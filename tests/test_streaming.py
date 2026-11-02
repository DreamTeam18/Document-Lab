import json

import httpx
import pytest

from app.config import Settings
from app.providers import ProviderError, Providers
from app.workflow import Workflow
from tests.test_core import FakeProvider, FakeSearch, hit


class Frames(httpx.AsyncByteStream):
    def __init__(self, frames):
        self.frames = frames
        self.closed = False

    async def __aiter__(self):
        for frame in self.frames:
            yield frame.encode()

    async def aclose(self):
        self.closed = True


def frame(text):
    return "data: " + json.dumps({"choices": [{"delta": {"content": text}}]}) + "\r\n\r\n"


async def test_provider_yields_before_completion_and_closes_on_cancel():
    frames = Frames([": heartbeat\n\n", frame("Hello "), frame("world"), "data: [DONE]\n\n"])

    def handler(request):
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, stream=frames)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = Providers(Settings(_env_file=None, openrouter_api_key="test"), client)
        stream = provider.stream_chat("system", "prompt")
        assert await anext(stream) == "Hello "
        assert not frames.closed
        await stream.aclose()
        assert frames.closed


@pytest.mark.parametrize(
    "ending", ["", 'data: {"error":{"message":"secret"}}\n\n', "data: invalid\n\n"]
)
async def test_broken_stream_raises_sanitized_error(ending):
    frames = Frames([frame("partial"), ending])
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=frames))
    ) as client:
        stream = Providers(Settings(_env_file=None, openrouter_api_key="test"), client).stream_chat(
            "s", "p"
        )
        assert await anext(stream) == "partial"
        with pytest.raises(ProviderError) as error:
            await anext(stream)
        assert "secret" not in str(error.value)
        assert frames.closed


async def test_complete_stream_preserves_unicode():
    frames = Frames([frame("Hello 🌍"), "data: [DONE]\n\n"])
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=frames))
    ) as client:
        provider = Providers(Settings(_env_file=None, openrouter_api_key="test"), client)
        assert [d async for d in provider.stream_chat("s", "p")] == ["Hello 🌍"]


class StreamingProvider(FakeProvider):
    async def stream_chat(self, *args):
        yield "Blue "
        yield "[1]"


async def test_workflow_emits_tokens_before_validated_final_update():
    provider = StreamingProvider(['{"queries":["q"]}', '{"sufficient":true}'])
    workflow = Workflow(provider, FakeSearch([hit()]), stream_answer=True)
    events = [
        event
        async for event in workflow.graph.astream(
            {"question": "q", "history": "", "document_ids": []}, stream_mode=["updates", "custom"]
        )
    ]
    tokens = [value["delta"] for mode, value in events if mode == "custom"]
    assert tokens == ["Blue ", "[1]"]
    assert events[-1][1]["answer"]["answer"] == "Blue [1]"
    assert events[-1][1]["answer"]["citations"]


@pytest.mark.parametrize("fail", [False, True])
def test_api_streams_tokens_and_only_persists_completed_answer(monkeypatch, fail):
    from uuid import uuid4

    from fastapi.testclient import TestClient

    from app.api import app, storage
    from app.config import settings
    from tests.test_providers_api import FakeStorage

    class Store(FakeStorage):
        async def search(self, *args):
            return [hit()]

    class Provider(StreamingProvider):
        async def stream_chat(self, *args):
            yield "Blue "
            if fail:
                raise ProviderError("Stream interrupted")
            yield "[1]"

    monkeypatch.setenv("DATABASE_URL", "")
    settings.cache_clear()
    store = Store()
    app.dependency_overrides[storage] = lambda: store
    try:
        with TestClient(app) as client:
            app.state.providers = Provider(['{"queries":["q"]}', '{"sufficient":true}'])
            response = client.post(
                "/query", json={"user_query": "q", "document_ids": [str(uuid4())]}
            )
            assert "event: token" in response.text
            if fail:
                assert "event: error" in response.text
                assert "event: result" not in response.text
                assert not store.saved
            else:
                assert response.text.index("event: token") < response.text.index("event: result")
                assert len(store.saved) == 1
                assert store.saved[0][3] == "Blue [1]"
    finally:
        app.dependency_overrides.clear()
        settings.cache_clear()
