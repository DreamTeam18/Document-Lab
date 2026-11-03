import asyncio
import copy
import json
from uuid import uuid4

import pytest

from app.agents.budget import CallBudget, current_budget
from app.agents.hyde import HyDEAgent
from app.config import Settings
from app.providers import ProviderError
from app.workflow import Workflow
from tests.test_core import assessment_fixture, hit

PASSAGE = "Hypothetical detail NEVER AUTHORITATIVE Section 9999"


def plan(question="What is the policy?"):
    return {
        "research_plan": [
            {
                "id": "q1",
                "question": question,
                "objective": "Find evidence",
                "dependencies": [],
                "document_ids": [],
            }
        ],
        "warnings": [],
    }


class Provider:
    def __init__(self, response=None, failure=None):
        self.response = response if response is not None else json.dumps({"passage": PASSAGE})
        self.failure = failure
        self.calls = []
        self.embedded = []

    async def chat(self, system, prompt, *args):
        self.calls.append((system, json.loads(prompt), args))
        if system.startswith("Classify"):
            return '{"route":"complex_research","rewritten_question":"What is the policy?"}'
        if system.startswith("You plan"):
            return json.dumps(
                {
                    "sub_questions": [
                        {k: v for k, v in plan()["research_plan"][0].items() if k != "document_ids"}
                    ]
                }
            )
        if system.startswith("Generate a hypothetical"):
            if self.failure:
                raise self.failure
            return self.response
        assert PASSAGE not in prompt
        return (
            assessment_fixture('{"sufficient":true}', prompt)
            if system.startswith("Check")
            else "Actual policy [1]"
        )

    async def embed(self, text):
        self.embedded.append(text)
        return [2.0 if text == PASSAGE else 1.0] * 768


class Store:
    def __init__(self, fail_hyde=False):
        self.calls = []
        self.fail_hyde = fail_hyde
        self.original, self.additional = hit(1), hit(2)
        self.original["text"] = "Original real source"
        self.additional["text"] = "Additional real source"

    async def search(self, query, ids, vector):
        self.calls.append((query, list(ids), vector))
        if vector[0] == 2:
            if self.fail_hyde:
                raise ProviderError("unavailable")
            return [{**h, "document_id": ids[0]} for h in [self.additional, self.original]]
        return [{**self.original, "document_id": ids[0]}]


def initial():
    return {"question": "What is the policy?", "history": "", "document_ids": [uuid4()]}


def test_default_is_disabled():
    assert not Settings(_env_file=None).hyde_enabled


async def test_generates_bounded_passage_without_mutating_state():
    original = plan()
    before = copy.deepcopy(original)
    provider = Provider()
    result = await HyDEAgent(provider)(original)
    assert result["hyde_passages"] == {"q1": PASSAGE}
    assert original == before
    assert provider.calls[0][2] == (300,)


@pytest.mark.parametrize(
    "response",
    [
        "bad json",
        "{}",
        "[]",
        '{"passage":null}',
        '{"passage":" "}',
        json.dumps({"passage": "x" * 2001}),
        '{"passage":"x","answer":"fabricated"}',
    ],
)
async def test_invalid_output_falls_back_without_evidence(response):
    result = await HyDEAgent(Provider(response))(plan())
    assert result["hyde_passages"] == {}
    assert result["warnings"]
    assert "sources" not in result


@pytest.mark.parametrize("retryable", [False, True])
async def test_generation_failure_uses_normal_retrieval_without_retrying(retryable):
    provider = Provider(failure=ProviderError("safe", retryable=retryable))
    store = Store()
    result = await Workflow(provider, store, hyde_enabled=True).graph.ainvoke(initial())
    assert result["status"] == "succeeded"
    assert len([c for c in provider.calls if c[0].startswith("Generate")]) == 1
    assert len(store.calls) == 1 and PASSAGE not in provider.embedded


async def test_real_vector_wiring_and_selected_scope_without_hypothesis_in_evidence():
    provider, store, request = Provider(), Store(), initial()
    result = await Workflow(provider, store, hyde_enabled=True).graph.ainvoke(request)
    assert result["status"] == "succeeded"
    assert provider.embedded == ["What is the policy?", PASSAGE]
    assert [c[2][0] for c in store.calls] == [1.0, 2.0]
    assert all(
        c[0] == "What is the policy?" and c[1] == request["document_ids"] for c in store.calls
    )
    assert "Additional real source" in result["context"]
    assert PASSAGE not in result["context"]
    assert PASSAGE not in json.dumps(result["sources"])
    assert result["hyde_passages"] == {}
    assert result["usage"]["chat_calls"] == 5
    assert result["usage"]["embedding_calls"] == 2
    assert len(result["hits"]) == 2


async def test_search_failure_retains_original_evidence():
    result = await Workflow(Provider(), Store(fail_hyde=True), hyde_enabled=True).graph.ainvoke(
        initial()
    )
    assert result["status"] == "succeeded"
    assert "Original real source" in result["context"]
    assert any("HyDE search unavailable" in w for w in result["warnings"])


async def test_hypothesis_embedding_failure_retains_original_evidence():
    class Broken(Provider):
        async def embed(self, text):
            if text == PASSAGE:
                raise ProviderError("bad vector")
            return await super().embed(text)

    store = Store()
    result = await Workflow(Broken(), store, hyde_enabled=True).graph.ainvoke(initial())
    assert result["status"] == "succeeded" and len(store.calls) == 1


@pytest.mark.parametrize(
    "question", ["What does section 4.2 say?", "Compare table 3 and table 4", "Explain chapter 5"]
)
async def test_exact_reference_plan_items_skip_hypothesis_generation(question):
    provider = Provider()
    result = await HyDEAgent(provider)(plan(question))
    assert result["hyde_passages"] == {} and not provider.calls


async def test_reserves_two_chat_calls_for_final_stages():
    token = current_budget.set(CallBudget(4, 13, chat_calls=2))
    try:
        provider = Provider()
        result = await HyDEAgent(provider)(plan())
        assert not provider.calls and not result["hyde_passages"]
        assert result["warnings"]
    finally:
        current_budget.reset(token)


async def test_low_embedding_budget_skips_optional_search():
    provider, store = Provider(), Store()
    result = await Workflow(
        provider, store, hyde_enabled=True, embedding_call_limit=1
    ).graph.ainvoke(initial())
    assert result["status"] == "succeeded"
    assert provider.embedded == ["What is the policy?"]
    assert any("HyDE embedding skipped" in w for w in result["warnings"])


async def test_cancellation_during_generation_is_propagated():
    entered = asyncio.Event()

    class Slow(Provider):
        async def chat(self, system, *args):
            if system.startswith("Generate"):
                entered.set()
                await asyncio.sleep(10)
            return await super().chat(system, *args)

    store = Store()
    task = asyncio.create_task(Workflow(Slow(), store, hyde_enabled=True).graph.ainvoke(initial()))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not store.calls


async def test_disabled_enabled_comparison_uses_identical_fixture_and_reports_added_calls():
    # Wiring/cost regression only, not a semantic-quality benchmark.
    results = []
    for enabled in [False, True]:
        provider, store = Provider(), Store()
        result = await Workflow(provider, store, hyde_enabled=enabled).graph.ainvoke(initial())
        results.append(result)
        assert len(store.calls) == (2 if enabled else 1)
    assert results[1]["usage"]["chat_calls"] == results[0]["usage"]["chat_calls"] + 1
    assert results[1]["usage"]["embedding_calls"] == results[0]["usage"]["embedding_calls"] + 1
    assert [h["text"] for h in results[0]["hits"]] == ["Original real source"]
    assert "Additional real source" in results[1]["context"]
