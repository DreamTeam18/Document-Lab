"""Agent contracts tested independently and through the unchanged graph."""

import asyncio
import copy
import json

import pytest

from app.agents import (
    AnsweringAgent,
    AssessmentAgent,
    PlanningAgent,
    RefinementAgent,
    RetrievalAgent,
    SearchService,
)
from app.agents.evidence import prepare_evidence
from app.providers import ProviderError
from app.workflow import Workflow
from tests.test_core import FakeProvider, FakeSearch, hit


def state():
    evidence = hit()
    context, sources = prepare_evidence([evidence])
    return {
        "question": "What color?",
        "history": "",
        "document_ids": [evidence["document_id"]],
        "searches": ["labels"],
        "hits": [evidence],
        "context": context,
        "sources": sources,
        "warnings": ["earlier warning"],
    }


def agent(name, provider, storage):
    search = SearchService(provider, storage)
    return {
        "plan": PlanningAgent(provider),
        "retrieve": RetrievalAgent(search),
        "assess": AssessmentAgent(provider),
        "refine": RefinementAgent(search),
        "answer": AnsweringAgent(provider),
    }[name]


@pytest.mark.parametrize(
    "name,reply,keys",
    [
        ("plan", '{"queries":["blue labels"]}', {"searches", "warnings"}),
        ("retrieve", "", {"hits", "context", "sources", "warnings"}),
        ("assess", '{"sufficient":false,"query":"colors"}', {"retry", "searches"}),
        ("refine", "", {"context", "sources", "warnings"}),
        ("answer", "Blue [1]", {"answer", "citations"}),
    ],
)
async def test_agents_return_patches_without_mutating_input(name, reply, keys):
    original = state()
    before = copy.deepcopy(original)
    provider = FakeProvider([reply])
    storage = FakeSearch([hit(2)])
    result = await agent(name, provider, storage)(original)
    assert original == before
    assert result is not original
    assert set(result) == keys
    if name == "plan":
        assert result["searches"] == ["blue labels"]
    elif name == "assess":
        assert result["retry"] is True
        assert result["searches"] == ["colors"]
    elif name == "answer":
        assert result["answer"] == "Blue [1]"
        assert result["citations"] == original["sources"]
    else:
        assert result["sources"][0]["document_id"] == str(storage.hits[0]["document_id"])


@pytest.mark.parametrize("name", ["plan", "retrieve", "assess", "refine", "answer"])
@pytest.mark.parametrize("error_type", [ProviderError, asyncio.CancelledError])
async def test_failure_and_cancellation_propagate_unchanged(name, error_type):
    error = error_type("injected failure")

    class FailingProvider:
        async def chat(self, *args):
            raise error

        async def embed(self, *args):
            return [1.0] * 768

    class FailingStorage:
        async def search(self, *args):
            raise error

    with pytest.raises(error_type) as raised:
        await agent(name, FailingProvider(), FailingStorage())(state())
    assert raised.value is error


async def test_embedding_fallback_preserves_document_scope():
    original = state()
    calls = []

    class ScopedStorage:
        async def search(self, query, document_ids, embedding):
            calls.append((query, list(document_ids), embedding))
            return original["hits"]

    service = SearchService(FakeProvider([], fail_embedding=True), ScopedStorage())
    result = await RetrievalAgent(service)(original)
    assert calls == [("labels", original["document_ids"], None)]
    assert result["warnings"] == ["Embedding service unavailable; used exact/full-text retrieval."]
    assert original["warnings"] == ["earlier warning"]


async def test_embedding_cancellation_is_not_converted_to_fallback():
    class CancelledProvider:
        async def embed(self, query):
            raise asyncio.CancelledError()

    storage = FakeSearch([])
    with pytest.raises(asyncio.CancelledError):
        await RetrievalAgent(SearchService(CancelledProvider(), storage))(state())
    assert storage.calls == []


@pytest.mark.parametrize("streaming", [False, True])
async def test_shared_workflow_isolates_concurrent_state_sources_and_tokens(streaming):
    records = {"blue": hit(1), "green": hit(2)}
    for color, record in records.items():
        record["text"] = color
    arrived = set()
    both_searching = asyncio.Event()

    class ScopedProvider:
        async def chat(self, system, prompt, *args):
            payload = json.loads(prompt)
            color = payload["question"]
            if system.startswith("Classify document"):
                return json.dumps({"route": "complex_research", "rewritten_question": color})
            if "plan document" in system:
                return json.dumps({"queries": [color]})
            if "Check whether" in system:
                return '{"sufficient":true}'
            return color + " [1]"

        async def embed(self, query):
            return [1.0] * 768

        async def stream_chat(self, system, prompt):
            yield json.loads(prompt)["question"]
            await asyncio.sleep(0)
            yield " [1]"

    class ScopedStorage:
        async def search(self, query, document_ids, embedding):
            assert document_ids == [records[query]["document_id"]]
            arrived.add(query)
            if len(arrived) == 2:
                both_searching.set()
            await asyncio.wait_for(both_searching.wait(), timeout=2)
            return [records[query]]

    workflow = Workflow(ScopedProvider(), ScopedStorage(), stream_answer=streaming)

    async def run(color):
        events = [
            event
            async for event in workflow.graph.astream(
                {"question": color, "history": "", "document_ids": [records[color]["document_id"]]},
                stream_mode=["updates", "custom"],
            )
        ]
        updates = [value for mode, value in events if mode == "updates"]
        assert [next(iter(value)) for value in updates] == [
            "triage",
            "plan",
            "retrieve",
            "assess",
            "answer",
        ]
        final = updates[-1]["answer"]
        assert final["answer"] == color + " [1]"
        assert final["citations"][0]["document_id"] == str(records[color]["document_id"])
        tokens = [value["delta"] for mode, value in events if mode == "custom"]
        assert tokens == ([color, " [1]"] if streaming else [])

    await asyncio.gather(run("blue"), run("green"))
