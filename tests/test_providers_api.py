import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import app, storage
from app.config import Settings, settings
from app.providers import ProviderError, Providers
from tests.test_core import FakeProvider


async def test_openrouter_request_and_sanitized_errors():
    def handler(request):
        assert request.url == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-secret"
        payload = json.loads(request.content)
        assert payload["model"] == "openrouter/free"
        assert "models" not in payload  # No hidden paid fallback.
        return httpx.Response(429, json={"error": "sensitive upstream information"})

    config = Settings(_env_file=None, openrouter_api_key="test-secret")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError, match="unavailable or rate-limited") as exc:
            await Providers(config, client).chat("system", "question")
        assert "sensitive" not in str(exc.value)


async def test_openrouter_embedding_request_and_normalization():
    def handler(request):
        assert request.url == "https://openrouter.ai/api/v1/embeddings"
        assert request.headers["Authorization"] == "Bearer test-secret"
        payload = json.loads(request.content)
        assert payload == {
            "model": "openai/text-embedding-3-small",
            "input": "text",
            "dimensions": 768,
        }
        return httpx.Response(200, json={"data": [{"embedding": [2.0] + [0.0] * 767}]})

    config = Settings(_env_file=None, openrouter_api_key="test-secret")
    assert config.embedding_signature == "openrouter:openai/text-embedding-3-small:768"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (await Providers(config, client).embed("text"))[0] == 1


async def test_embeddings_require_openrouter_key():
    async with httpx.AsyncClient() as client:
        with pytest.raises(ProviderError, match="OPENROUTER_API_KEY"):
            await Providers(Settings(_env_file=None, openrouter_api_key=""), client).embed("text")


class FakeStorage:
    def __init__(self):
        self.saved = []

    async def documents(self):
        return []

    async def history(self, *args):
        return []

    async def conversation(self, *args):
        return uuid4(), 0, []

    async def search(self, *args):
        return []

    async def save_turn(self, *args):
        self.saved.append(args)


def test_no_token_required_and_stream_persistence(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    settings.cache_clear()
    store = FakeStorage()
    app.dependency_overrides[storage] = lambda: store
    try:
        with TestClient(app) as client:
            assert client.get("/", follow_redirects=False).status_code == 307
            assert (
                client.get("/chat", follow_redirects=False)
                .headers["location"]
                .endswith("/workspace/chats/new")
            )
            landing = client.get("/legacy")
            assert landing.status_code == 200
            assert 'href="/chat"' in landing.text
            page = client.get("/legacy/chat")
            assert page.status_code == 200
            assert "Document Lab" in page.text
            assert "APP_API_KEY" not in page.text
            assert 'id="token"' not in page.text
            assert "/static/app.js?v=5" in page.text
            for asset in ("app.js?v=5", "stream.js", "style.css"):
                response = client.get(f"/static/{asset}")
                assert response.status_code == 200
                assert response.headers["cache-control"] == "no-store"
            assert client.get("/static/style.css").status_code == 200
            assert client.get("/health").status_code == 200
            assert client.get("/documents").json() == []
            assert client.get(f"/conversations/{uuid4()}/messages").json() == []
            assert "securitySchemes" not in client.get("/openapi.json").json()["components"]
            app.state.providers = FakeProvider(
                [
                    '{"sub_questions":[{"id":"q1","question":"missing","objective":"Find supporting evidence","dependencies":[]}]}',
                    '{"sufficient":true}',
                ]
            )
            response = client.post(
                "/query",
                json={"user_query": "missing", "document_ids": [str(uuid4())]},
            )
            assert response.status_code == 200
            assert "event: session" in response.text
            assert "event: result" in response.text
            assert "event: error" not in response.text
            assert len(store.saved) == 1
    finally:
        app.dependency_overrides.clear()
        settings.cache_clear()
