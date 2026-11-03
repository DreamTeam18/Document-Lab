import asyncio
import copy
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.budget import current_budget
from app.agents.planning import PlanningAgent, normalize_plan
from app.config import Settings
from app.providers import ProviderError
from app.workflow import Workflow
from tests.test_core import FakeProvider, FakeSearch, assessment_fixture, hit


def item(id="a", question="What is the policy?", dependencies=None):
    return {
        "id": id,
        "question": question,
        "objective": "Find policy evidence",
        "dependencies": dependencies or [],
    }


def state(question="Compare policies"):
    return {"question": question, "history": "", "document_ids": [uuid4()]}


def envelope(*items):
    return json.dumps({"sub_questions": list(items)})


@pytest.mark.parametrize(
    "items",
    [
        [item()],
        [item("a", "What is annual leave?"), item("b", "What is sick leave?")],
        [item("a", "What is the limit?"), item("b", "What exceptions apply?", ["a"])],
    ],
)
async def test_reviewed_question_shapes_produce_valid_scoped_plans(items):
    original = state()
    before = copy.deepcopy(original)
    result = await PlanningAgent(FakeProvider([envelope(*items)]))(original)
    assert result["plan_size"] == len(items)
    assert not result["plan_fallback"]
    assert original == before
    for index, question in enumerate(result["research_plan"]):
        assert question["id"] == f"q{index + 1}"
        assert question["document_ids"] == original["document_ids"]
        assert question["objective"]
    assert result["searches"] == [i["question"] for i in items]


@pytest.mark.parametrize(
    "raw",
    [
        "invalid",
        "{}",
        "[]",
        '{"queries":["old shape"]}',
        envelope(),
        envelope(item("same"), item("same", "Different question")),
        envelope(item("a", dependencies=["missing"])),
        envelope(item("a", dependencies=["a"])),
        envelope(item("a", dependencies=["b"]), item("b", "Second question", ["a"])),
        envelope({**item(), "question": " "}),
        envelope({**item(), "objective": ""}),
        envelope({**item(), "dependencies": "a"}),
        envelope({**item(), "document_ids": ["unselected"]}),
        envelope(item("a"), item("b", "Second"), item("c", "Third")),
    ],
)
async def test_invalid_plans_fall_back_to_original_question(raw):
    original = state("What does section 3.2 require?")
    result = await PlanningAgent(FakeProvider([raw]))(original)
    assert result["plan_fallback"]
    assert result["searches"] == [original["question"]]
    assert result["research_plan"][0]["dependencies"] == []
    assert result["research_plan"][0]["document_ids"] == original["document_ids"]


async def test_deduplication_remaps_dependencies_and_orders_execution():
    plan = normalize_plan(
        {
            "sub_questions": [
                item("last", "What exceptions apply?", ["alias"]),
                item("first", "What is the limit?"),
                item("alias", "  WHAT is the limit?  "),
            ]
        },
        state(),
        4,
    )
    assert [p["id"] for p in plan] == ["q1", "q2"]
    assert plan[0]["question"] == "What is the limit?"
    assert plan[1]["dependencies"] == ["q1"]


async def test_explicit_references_survive_and_missing_references_fall_back():
    original = state("Compare sections 3.2 and 4.1")
    good = envelope(
        item("a", "What does section 3.2 say?"), item("b", "What does section 4.1 say?")
    )
    result = await PlanningAgent(FakeProvider([good]))(original)
    assert not result["plan_fallback"]
    bad = await PlanningAgent(FakeProvider([envelope(item())]))(original)
    assert bad["plan_fallback"]


async def test_configurable_four_question_plan_and_stable_ids():
    raw = {"sub_questions": [item(str(i), f"Question {i}") for i in range(4)]}
    original = state()
    assert normalize_plan(raw, original, 4) == normalize_plan(raw, original, 4)
    with pytest.raises(ValueError):
        normalize_plan(raw, original, 2)
    assert (await PlanningAgent(FakeProvider([json.dumps(raw)]), 4)(original))["plan_size"] == 4


@pytest.mark.parametrize(
    "setting,value",
    [
        ("max_sub_questions", 0),
        ("max_sub_questions", 5),
        ("chat_call_limit", 0),
        ("embedding_call_limit", 25),
    ],
)
def test_settings_reject_unbounded_or_invalid_limits(setting, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{setting: value})


async def test_planner_provider_failure_uses_original_question():
    class Broken:
        async def chat(self, *args):
            raise ProviderError("no response")

    result = await PlanningAgent(Broken())(state("Original question"))
    assert result["plan_fallback"] and result["searches"] == ["Original question"]


async def test_planner_bounds_history_and_preserves_original_intent_in_prompt():
    class Capture:
        async def chat(self, system, prompt, *args):
            data = json.loads(prompt)
            assert data["question"] == "Resolved followup"
            assert data["original_question"] == "What about exceptions?"
            assert len(data["recent_history"]) == 6000
            return envelope(item(question="Resolved followup"))

    original = state("What about exceptions?") | {
        "history": "x" * 7000,
        "resolved_question": "Resolved followup",
    }
    await PlanningAgent(Capture())(original)


class ResearchProvider:
    def __init__(self, plan):
        self.plan = plan
        self.chat_calls = 0
        self.embedding_calls = 0

    async def chat(self, system, *args):
        self.chat_calls += 1
        if system.startswith("Classify"):
            return '{"route":"complex_research","rewritten_question":"Compare policies"}'
        if system.startswith("You plan"):
            return self.plan
        if system.startswith("Check"):
            return assessment_fixture('{"sufficient":true}', args[0])
        return "Blue [1]"

    async def embed(self, text):
        self.embedding_calls += 1
        await asyncio.sleep(0)
        return [1.0] * 768


async def test_graph_executes_dependencies_first_and_retains_results_by_id():
    provider = ResearchProvider(envelope(item("b", "Dependent", ["a"]), item("a", "Foundation")))
    store = FakeSearch([hit()])
    result = await Workflow(provider, store).graph.ainvoke(state())
    assert result["status"] == "succeeded"
    assert [q for q, _ in store.calls] == ["Foundation", "Dependent"]
    assert [r["sub_question_id"] for r in result["research_results"]] == ["q1", "q2"]
    assert result["plan_size"] == 2
    assert result["usage"]["chat_calls"] == provider.chat_calls == 4
    assert result["usage"]["embedding_calls"] == provider.embedding_calls == 2
    assert current_budget.get() is None


@pytest.mark.parametrize(
    "limits,kind,expected",
    [
        ({"chat_call_limit": 2}, "chat_calls", 2),
        ({"embedding_call_limit": 1}, "embedding_calls", 1),
    ],
)
async def test_budget_exhaustion_is_terminal_before_another_provider_call(limits, kind, expected):
    provider = ResearchProvider(envelope(item("a", "First"), item("b", "Second")))
    result = await Workflow(provider, FakeSearch([hit()]), **limits).graph.ainvoke(state())
    assert result["status"] == "failed"
    assert result["failure"]["code"] == "budget_exceeded"
    assert result["usage"][kind] == getattr(provider, kind) == expected
    assert result["answer"] == ""
    assert current_budget.get() is None


async def test_failed_provider_attempts_consume_shared_budget_before_retry():
    class Flaky(ResearchProvider):
        async def chat(self, *args):
            self.chat_calls += 1
            raise ProviderError("transient", retryable=True)

    provider = Flaky("")
    result = await Workflow(provider, FakeSearch([]), chat_call_limit=1).graph.ainvoke(state())
    assert provider.chat_calls == result["usage"]["chat_calls"] == 1
    assert result["failure"]["code"] == "budget_exceeded"


async def test_parallel_invocations_have_separate_call_budgets():
    provider = ResearchProvider(envelope(item("a", "First"), item("b", "Second")))
    workflow = Workflow(provider, FakeSearch([hit()]), chat_call_limit=4, embedding_call_limit=2)
    results = await asyncio.gather(workflow.graph.ainvoke(state()), workflow.graph.ainvoke(state()))
    assert all(r["status"] == "succeeded" for r in results)
    assert all(
        r["usage"]["chat_calls"] == 4 and r["usage"]["embedding_calls"] == 2 for r in results
    )
    assert provider.chat_calls == 8
    assert current_budget.get() is None


async def test_four_question_graph_obeys_configured_limit():
    provider = ResearchProvider(envelope(*(item(str(i), f"Question {i}") for i in range(4))))
    store = FakeSearch([hit()])
    result = await Workflow(provider, store, max_sub_questions=4).graph.ainvoke(state())
    assert result["status"] == "succeeded"
    assert result["plan_size"] == len(store.calls) == 4
    assert result["usage"]["embedding_calls"] == 4


async def test_streaming_generation_consumes_chat_budget():
    class Streaming(ResearchProvider):
        stream_calls = 0

        async def stream_chat(self, *args):
            self.stream_calls += 1
            yield "Blue [1]"

    provider = Streaming(envelope(item()))
    result = await Workflow(provider, FakeSearch([hit()]), stream_answer=True).graph.ainvoke(
        state()
    )
    assert result["status"] == "succeeded"
    assert result["usage"]["chat_calls"] == provider.chat_calls + provider.stream_calls == 4


@pytest.mark.parametrize("limit,success", [(1, False), (6, True)])
def test_api_exposes_usage_and_does_not_save_exhausted_requests(monkeypatch, limit, success):
    from fastapi.testclient import TestClient

    from app.api import app, storage
    from app.config import settings
    from tests.test_providers_api import FakeStorage

    class Store(FakeStorage):
        async def search(self, *args):
            return [{**hit(), "document_id": args[1][0]}]

    class Provider(ResearchProvider):
        async def stream_chat(self, *args):
            yield "Blue [1]"

    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("CHAT_CALL_LIMIT", str(limit))
    settings.cache_clear()
    store = Store()
    app.dependency_overrides[storage] = lambda: store
    try:
        with TestClient(app) as client:
            app.state.providers = Provider(envelope(item()))
            response = client.post(
                "/query", json={"user_query": "Compare policies", "document_ids": [str(uuid4())]}
            )
        terminal = [
            json.loads(frame.split("data: ", 1)[1])
            for frame in response.text.split("\n\n")
            if frame.startswith("event: result") or frame.startswith("event: error")
        ]
        assert len(terminal) == 1
        assert terminal[0]["usage"]["chat_limit"] == limit
        assert terminal[0]["usage"]["chat_calls"] == (4 if success else 1)
        assert len(store.saved) == int(success)
        if success:
            assert terminal[0]["plan_size"] == 1
        else:
            assert "event: result" not in response.text
            assert "budget exhausted" in terminal[0]["message"]
    finally:
        app.dependency_overrides.clear()
        settings.cache_clear()
