import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import app, storage
from app.config import Settings, settings
from app.providers import ProviderError, Providers
from app.storage import Conflict, NotFound
from app.workflow import Workflow, grounded_citations
from tests.test_core import FakeProvider, FakeSearch, hit
from tests.test_providers_api import FakeStorage


@pytest.mark.parametrize("answer", ["Blue 【1】", "Blue ［1］", "Blue [1]"])
def test_equivalent_citation_formats(answer):
    text, citations = grounded_citations(answer, [{"citation": 1}])
    assert text == "Blue [1]"
    assert citations == [{"citation": 1}]


def test_unicode_invalid_citation_still_rejected():
    assert grounded_citations("Blue 【999】", [{"citation": 1}])[1] == []


def test_explicit_insufficient_evidence_is_not_a_citation_error():
    answer, citations = grounded_citations("INSUFFICIENT_EVIDENCE", [{"citation": 1}])
    assert "do not contain enough evidence" in answer
    assert citations == []


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        "invalid",
        {"data": [None]},
        {"data": {}},
        {"data": ["bad"]},
        {"data": [{"embedding": [0] * 768}]},
        {"data": [{"embedding": [1e308] * 768}]},
        {"data": [{"embedding": [1, 2]}]},
    ],
)
async def test_malformed_embeddings_are_safe_provider_errors(body):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=json.dumps(body)))
    ) as client:
        with pytest.raises(ProviderError):
            await Providers(Settings(_env_file=None, openrouter_api_key="test"), client).embed("x")


@pytest.mark.parametrize("status", [401, 402, 429, 500, 503])
async def test_provider_status_never_exposes_response_secrets(status):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, text="secret-upstream-body")
        )
    ) as client:
        with pytest.raises(ProviderError) as error:
            await Providers(Settings(_env_file=None, openrouter_api_key="test"), client).chat(
                "s", "q"
            )
        assert "secret-upstream-body" not in str(error.value)


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "1")
    settings.cache_clear()
    store = FakeStorage()
    app.dependency_overrides[storage] = lambda: store
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, store
    app.dependency_overrides.clear()
    settings.cache_clear()


def payload():
    return {"user_query": "What color?", "document_ids": [str(uuid4())]}


@pytest.mark.parametrize(
    "change",
    [
        {"user_query": " "},
        {"user_query": "x" * 4001},
        {"document_ids": []},
        {"document_ids": ["bad-uuid"]},
        {"document_ids": [str(uuid4()) for _ in range(6)]},
        {"thread_id": "bad-uuid"},
    ],
)
def test_api_validation(api, change):
    client, store = api
    assert client.post("/query", json=payload() | change).status_code == 422
    assert store.saved == []


@pytest.mark.parametrize("error, status", [(NotFound("missing"), 404), (Conflict("changed"), 409)])
def test_preflight_failures_use_http_status(api, error, status):
    client, store = api

    async def fail(*args):
        raise error

    store.conversation = fail
    assert client.post("/query", json=payload()).status_code == status


@pytest.mark.parametrize("mode", ["provider", "internal", "timeout", "conflict"])
def test_stream_failures_do_not_emit_result_or_save_partial_turn(api, mode):
    client, store = api

    class Broken:
        async def chat(self, *args):
            if mode == "timeout":
                await asyncio.sleep(3)
            if mode == "provider":
                raise ProviderError("Model unavailable")
            raise RuntimeError("private-password")

    app.state.providers = Broken()
    if mode == "conflict":
        app.state.providers = FakeProvider(
            [
                '{"sub_questions":[{"id":"q1","question":"q","objective":"Find supporting evidence","dependencies":[]}]}',
                '{"sufficient":true}',
            ]
        )

        async def conflict(*args):
            raise Conflict("Concurrent turn")

        store.save_turn = conflict
    response = client.post("/query", json=payload())
    assert response.status_code == 200
    assert "event: error" in response.text
    assert "event: result" not in response.text
    assert "private-password" not in response.text
    assert store.saved == []


@pytest.mark.parametrize(
    "path",
    [
        "/.env",
        "/static/.env",
        "/static/../.env",
        "/static/%2e%2e/.env",
        "/.local/pgdata/pg_hba.conf",
    ],
)
def test_private_files_not_served(api, path):
    client, _ = api
    assert client.get(path).status_code == 404


async def test_excessive_plan_is_bounded_and_invalid_citations_rejected():
    provider = FakeProvider(
        [json.dumps({"queries": ["q"] * 50}), '{"sufficient":true}', "Unsupported [99]"]
    )
    store = FakeSearch([hit()])
    result = await Workflow(provider, store).graph.ainvoke(
        {"question": "q", "history": "", "document_ids": [uuid4()]}
    )
    assert len(store.calls) <= 2
    assert result["citations"] == []
    assert "Unsupported" not in result["answer"]
