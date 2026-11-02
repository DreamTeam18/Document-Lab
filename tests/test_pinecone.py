import json
from uuid import uuid4

import httpx
import pytest

from app.config import Settings
from app.pinecone import PineconeVectors, vector_record
from app.providers import ProviderError


def config():
    return Settings(_env_file=None, pinecone_key="test-secret")


def service(handler):
    return PineconeVectors(config(), httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_connection_validates_index():
    v = service(
        lambda r: httpx.Response(
            200,
            json={
                "dimension": 768,
                "metric": "cosine",
                "status": {"ready": True},
                "host": "test.svc.pinecone.io",
            },
        )
    )
    async with v.client:
        await v.connect()
        assert v.host == "https://test.svc.pinecone.io"


@pytest.mark.parametrize(
    "change",
    [
        {"dimension": 1536},
        {"metric": "dotproduct"},
        {"status": {"ready": False}},
        {"host": "evil.example"},
    ],
)
async def test_rejects_incompatible_index(change):
    info = {
        "dimension": 768,
        "metric": "cosine",
        "status": {"ready": True},
        "host": "x.pinecone.io",
        **change,
    }
    v = service(lambda r: httpx.Response(200, json=info))
    async with v.client:
        with pytest.raises(ProviderError):
            await v.connect()


async def test_query_filters_documents_generation_and_embedding_model():
    doc, generation = uuid4(), uuid4()

    def handler(request):
        payload = json.loads(request.content)
        assert payload["namespace"] == "rag-clone"
        assert payload["topK"] == 6
        assert str(doc) in json.dumps(payload["filter"])
        assert str(generation) in json.dumps(payload["filter"])
        assert config().embedding_signature in json.dumps(payload["filter"])
        assert request.headers["Api-Key"] == "test-secret"
        return httpx.Response(200, json={"matches": [{"id": "19"}, {"id": "2"}]})

    v = service(handler)
    v.host = "https://x.pinecone.io"
    async with v.client:
        assert await v.query([1.0] * 768, [(doc, generation)]) == [19, 2]


async def test_empty_scope_never_queries_all_documents():
    v = service(lambda r: pytest.fail("unscoped request"))
    async with v.client:
        assert await v.query([1.0] * 768, []) == []


async def test_upsert_batches_and_validates_acknowledgement():
    counts = []

    def handler(r):
        batch = json.loads(r.content)["vectors"]
        counts.append(len(batch))
        return httpx.Response(200, json={"upsertedCount": len(batch)})

    v = service(handler)
    v.host = "https://x.pinecone.io"
    async with v.client:
        await v.upsert([vector_record(i, uuid4(), uuid4(), [1.0] * 768, "sig") for i in range(205)])
    assert counts == [100, 100, 5]


async def test_errors_do_not_expose_provider_body_or_key():
    v = service(lambda r: httpx.Response(401, text="test-secret sensitive provider response"))
    async with v.client:
        with pytest.raises(ProviderError) as caught:
            await v.connect()
    assert "test-secret" not in str(caught.value)
    assert "sensitive" not in str(caught.value)


async def test_partial_upsert_is_failure():
    v = service(lambda r: httpx.Response(200, json={"upsertedCount": 0}))
    v.host = "https://x.pinecone.io"
    async with v.client:
        with pytest.raises(ProviderError):
            await v.upsert([vector_record(1, uuid4(), uuid4(), [1.0] * 768, "sig")])


async def test_visibility_checks_all_ids():
    v = service(lambda r: httpx.Response(200, json={"vectors": {"1": {}, "2": {}}}))
    v.host = "https://x.pinecone.io"
    async with v.client:
        await v.wait_visible([{"id": "1"}, {"id": "2"}])


async def test_bad_vector_is_rejected_before_network():
    v = service(lambda r: pytest.fail("invalid vector sent"))
    async with v.client:
        with pytest.raises(ProviderError):
            await v.query([float("nan")] * 768, [(uuid4(), uuid4())])
