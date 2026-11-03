"""Recovery tests use real graph execution with deterministic provider failures."""

import asyncio
import json
import time
from dataclasses import replace

import httpx
import pytest
from psycopg import OperationalError

from app.agents.recovery import ErrorHandlerAgent
from app.config import Settings
from app.pinecone import PineconeVectors
from app.providers import ProviderError, Providers
from app.workflow import Workflow
from tests.test_core import FakeProvider, FakeSearch, assessment_fixture, hit

INPUT = {"question": "q", "history": "", "document_ids": [__import__("uuid").uuid4()]}


class FlakyProvider:
    def __init__(self, failures):
        self.failures = dict(failures)
        self.calls = []

    async def chat(self, system, *args):
        if system.startswith("Classify document"):
            return '{"route":"complex_research","rewritten_question":"q"}'
        stage = (
            "plan"
            if "plan document" in system
            else "assess"
            if "Check whether" in system
            else "answer"
        )
        self.calls.append(stage)
        if self.failures.get(stage, 0):
            self.failures[stage] -= 1
            raise ProviderError("private-provider-body", retryable=True)
        return {
            "plan": '{"sub_questions":[{"id":"q1","question":"q","objective":"Find supporting evidence","dependencies":[]}]}',
            "assess": assessment_fixture('{"sufficient":true}', args[0])
            if stage == "assess"
            else "",
            "answer": "Blue [1]",
        }[stage]

    async def embed(self, query):
        return [1.0] * 768


async def run(workflow):
    events = [
        event async for event in workflow.graph.astream(INPUT, stream_mode=["updates", "custom"])
    ]
    final = {}
    stages = []
    for mode, event in events:
        if mode == "updates":
            for stage, patch in event.items():
                stages.append(stage)
                final.update(patch)
    return final, stages, events


@pytest.mark.parametrize("stage", ["plan", "assess"])
async def test_transient_provider_failure_reenters_actual_failed_node(stage):
    provider = FlakyProvider({stage: 1})
    final, stages, _ = await run(Workflow(provider, FakeSearch([hit()])))
    assert final["status"] == "succeeded"
    assert final["failure"] is None
    assert final["recovery_attempts"] == 1
    i = stages.index(stage)
    assert stages[i : i + 3] == [stage, "error_handler", stage]
    assert provider.calls.count(stage) == 2


async def test_retry_allowance_is_shared_across_nodes_and_exhaustion_is_terminal():
    provider = FlakyProvider({"plan": 1, "assess": 2})
    final, stages, _ = await run(Workflow(provider, FakeSearch([hit()])))
    assert final["status"] == "failed"
    assert final["recovery_attempts"] == 2
    assert stages[-1] == "error_handler"
    assert "answer" not in stages
    assert final["answer"] == "" and final["citations"] == []
    assert "private-provider-body" not in json.dumps(final, default=str)


async def test_planner_exhausts_three_attempts_then_uses_original_question():
    provider = FlakyProvider({"plan": 100})
    final, stages, _ = await run(Workflow(provider, FakeSearch([])))
    assert provider.calls == ["plan"] * 3
    assert stages == ["triage"] + ["plan", "error_handler"] * 3 + ["retrieve", "assess", "answer"]
    assert final["status"] == "succeeded"
    assert final["plan_fallback"] and final["searches"] == ["q"]


@pytest.mark.parametrize("stage", ["retrieve", "refine"])
async def test_storage_transient_failure_routes_back_to_same_research_stage(stage):
    replies = [
        '{"sub_questions":[{"id":"q1","question":"q","objective":"Find supporting evidence","dependencies":[]}]}',
        '{"sufficient":false,"query":"refined"}' if stage == "refine" else '{"sufficient":true}',
        *(['{"sufficient":true}'] if stage == "refine" else []),
        "Blue [1]",
    ]

    class Store:
        failed = False

        async def search(self, query, *args):
            if not self.failed and (stage == "retrieve" or query == "refined"):
                self.failed = True
                raise ProviderError("pinecone", retryable=True)
            return [{**hit(), "document_id": args[0][0]}]

    final, stages, _ = await run(Workflow(FakeProvider(replies), Store()))
    assert final["status"] == "succeeded"
    i = stages.index("error_handler")
    assert stages[i - 1 : i + 2] == [stage, "error_handler", stage]


@pytest.mark.parametrize(
    "failure",
    [OperationalError("secret dsn"), RuntimeError("secret body"), ProviderError("secret config")],
)
async def test_nontransient_storage_failures_are_sanitized_and_not_retried(failure, caplog):
    class Store:
        calls = 0

        async def search(self, *args):
            self.calls += 1
            raise failure

    store = Store()
    final, stages, _ = await run(Workflow(FlakyProvider({}), store))
    assert store.calls == 1
    assert stages == ["triage", "plan", "retrieve", "error_handler"]
    assert final["status"] == "failed"
    assert "secret" not in json.dumps(final, default=str) + caplog.text


@pytest.mark.parametrize(
    "reply", ["broken json", "{}", '{"sufficient":"true"}', '{"sufficient":false}']
)
async def test_malformed_assessment_reassesses_once_then_abstains(reply):
    provider = FakeProvider(
        [
            '{"sub_questions":[{"id":"q1","question":"q","objective":"Find supporting evidence","dependencies":[]}]}',
            reply,
            reply,
        ]
    )
    final, stages, _ = await run(Workflow(provider, FakeSearch([hit()])))
    assert final["status"] == "succeeded"
    assert final["assessments"][0]["status"] == "assessment_error"
    assert final["citations"] == []
    assert final["hits"]  # Useful evidence retained, not promoted to sufficient.
    assert provider.calls == 3
    assert stages[-3:] == ["refine", "assess", "answer"]


async def test_malformed_plan_retains_bounded_original_question_fallback():
    final, _, _ = await run(
        Workflow(FakeProvider(["not json", '{"sufficient":true}', "Blue [1]"]), FakeSearch([hit()]))
    )
    assert final["searches"] == ["q"]
    assert final["status"] == "succeeded"


async def test_standalone_graph_deadline_cancels_inflight_node():
    cancelled = asyncio.Event()

    class SlowProvider:
        async def chat(self, *args):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()

    final, stages, _ = await run(Workflow(SlowProvider(), FakeSearch([]), timeout_seconds=0.02))
    assert cancelled.is_set()
    assert final["failure"]["code"] == "deadline_exceeded"
    assert final["status"] == "failed"
    assert stages == ["triage", "error_handler"]


async def test_retry_backoff_does_not_exceed_remaining_deadline():
    final, stages, _ = await run(
        Workflow(FlakyProvider({"plan": 10}), FakeSearch([]), timeout_seconds=0.02)
    )
    assert stages == ["triage", "plan", "error_handler"]
    assert final["status"] == "failed"


async def test_cancellation_during_backoff_propagates():
    task = asyncio.create_task(
        replace(ErrorHandlerAgent(), retry_delay=1)(
            {
                "failure": {"stage": "plan", "code": "provider_failure", "retryable": True},
                "deadline": time.monotonic() + 10,
            }
        )
    )
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_cancelled_graph_never_retries():
    entered = asyncio.Event()

    class Provider:
        calls = 0

        async def chat(self, *args):
            self.calls += 1
            entered.set()
            await asyncio.sleep(10)

    provider = Provider()
    task = asyncio.create_task(run(Workflow(provider, FakeSearch([]))))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert provider.calls == 1


async def test_partial_stream_failure_never_replays_tokens():
    class Provider(FlakyProvider):
        stream_calls = 0

        async def stream_chat(self, *args):
            self.stream_calls += 1
            yield "partial "
            raise ProviderError("secret", retryable=True)

    provider = Provider({})
    final, stages, events = await run(Workflow(provider, FakeSearch([hit()]), stream_answer=True))
    assert provider.stream_calls == 1
    assert [v for mode, v in events if mode == "custom"] == [{"delta": "partial "}]
    assert stages[-2:] == ["answer", "error_handler"]
    assert final["status"] == "failed"
    assert final["answer"] == ""


@pytest.mark.parametrize("service", ["openrouter", "pinecone"])
@pytest.mark.parametrize(
    "status,retryable", [(401, False), (403, False), (400, False), (429, True), (503, True)]
)
async def test_http_classification_uses_status_not_raw_response(service, status, retryable):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(status, text="secret"))
    ) as client:
        config = Settings(_env_file=None, openrouter_api_key="test", pinecone_key="test")
        with pytest.raises(ProviderError) as raised:
            if service == "openrouter":
                await Providers(config, client).chat("system", "question")
            else:
                await PineconeVectors(config, client).request("GET", "https://example.com")
        assert raised.value.retryable is retryable
        assert "secret" not in str(raised.value)


async def test_provider_timeout_is_classified_transient():
    def fail(request):
        raise httpx.ReadTimeout("secret", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(ProviderError) as raised:
            await Providers(Settings(_env_file=None, openrouter_api_key="test"), client).chat(
                "s", "q"
            )
        assert raised.value.retryable
        assert "secret" not in str(raised.value)


@pytest.mark.parametrize("mode", ["recovered", "exhausted", "partial", "conflict", "sql"])
def test_api_terminal_status_controls_single_persistence_attempt(monkeypatch, mode):
    from uuid import uuid4

    from fastapi.testclient import TestClient

    from app.api import app, storage
    from app.config import settings
    from app.storage import Conflict
    from tests.test_providers_api import FakeStorage

    class Store(FakeStorage):
        writes = 0

        async def search(self, *args):
            return [{**hit(), "document_id": args[1][0]}]

        async def save_turn(self, *args):
            self.writes += 1
            if mode == "conflict":
                raise Conflict("Concurrent turn")
            if mode == "sql":
                raise OperationalError("secret SQL connection")
            await super().save_turn(*args)

    class Provider(FlakyProvider):
        stream_calls = 0

        async def stream_chat(self, *args):
            self.stream_calls += 1
            yield "Blue "
            if mode == "partial":
                raise ProviderError("secret provider body", retryable=True)
            yield "[1]"

    provider = Provider({"plan": 1, **({"assess": 10} if mode == "exhausted" else {})})
    store = Store()
    monkeypatch.setenv("DATABASE_URL", "")
    settings.cache_clear()
    app.dependency_overrides[storage] = lambda: store
    try:
        with TestClient(app) as client:
            app.state.providers = provider
            response = client.post(
                "/query", json={"user_query": "q", "document_ids": [str(uuid4())]}
            )
        assert "secret" not in response.text
        assert "error_handler" in response.text
        if mode == "recovered":
            assert response.text.count("event: result") == 1
            assert "event: error" not in response.text
            assert store.writes == len(store.saved) == 1
        else:
            assert response.text.count("event: error") == 1
            assert "event: result" not in response.text
            assert not store.saved
            assert store.writes == (1 if mode in {"conflict", "sql"} else 0)
        assert provider.stream_calls == (0 if mode == "exhausted" else 1)
        assert provider.calls.count("plan") == 2
    finally:
        app.dependency_overrides.clear()
        settings.cache_clear()


async def test_cancelling_stream_cleans_up_generator_without_recovery():
    entered, closed = asyncio.Event(), asyncio.Event()

    class Provider(FlakyProvider):
        stream_calls = 0

        async def stream_chat(self, *args):
            self.stream_calls += 1
            try:
                yield "partial"
                entered.set()
                await asyncio.sleep(10)
            finally:
                closed.set()

    provider = Provider({})
    task = asyncio.create_task(run(Workflow(provider, FakeSearch([hit()]), stream_answer=True)))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()
    assert provider.stream_calls == 1
