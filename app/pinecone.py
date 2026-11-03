"""Pinecone vector API; text and citation authority remain in PostgreSQL."""

import asyncio
import re

import httpx

from app.providers import ProviderError, transient_http_error, vector_literal


class PineconeVectors:
    def __init__(self, config, client):
        self.config, self.client = config, client
        self.host = None

    async def request(self, method, url, **kwargs):
        key = self.config.pinecone_key.get_secret_value()
        if not key:
            raise ProviderError("PINECONE_KEY is not configured")
        try:
            response = await self.client.request(
                method, url, headers={"Api-Key": key, "X-Pinecone-Api-Version": "2025-10"}, **kwargs
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(
                "Pinecone request failed; check connectivity and index configuration",
                retryable=transient_http_error(exc),
            ) from None
        except ValueError:
            raise ProviderError(
                "Pinecone request failed; check connectivity and index configuration"
            ) from None

    async def connect(self):
        body = await self.request(
            "GET", "https://api.pinecone.io/indexes/" + self.config.pinecone_index
        )
        if (
            body.get("dimension") != self.config.embedding_dimensions
            or body.get("metric") != "cosine"
        ):
            raise ProviderError("Pinecone index must use matching dimensions and cosine similarity")
        if not body.get("status", {}).get("ready"):
            raise ProviderError("Pinecone index is not ready")
        host = body.get("host", "")
        if not re.fullmatch(r"[a-zA-Z0-9.-]+\.pinecone\.io", host):
            raise ProviderError("Pinecone returned an invalid index host")
        self.host = "https://" + host

    async def data(self, path, payload):
        if not self.host:
            await self.connect()
        return await self.request(
            "POST", self.host + path, json={"namespace": self.config.pinecone_namespace, **payload}
        )

    async def upsert(self, records):
        for start in range(0, len(records), 100):
            batch = records[start : start + 100]
            for record in batch:
                vector_literal(record["values"], self.config.embedding_dimensions)
            result = await self.data("/vectors/upsert", {"vectors": batch})
            if result.get("upsertedCount") != len(batch):
                raise ProviderError("Pinecone did not acknowledge all vectors")

    async def wait_visible(self, records):
        # Pinecone writes are eventually consistent. Do not publish a new document
        # generation in SQL until its vector IDs can be fetched.
        if not records:
            return
        for attempt in range(20):
            visible = True
            for start in range(0, len(records), 100):
                ids = [r["id"] for r in records[start : start + 100]]
                result = await self.request(
                    "GET",
                    self.host + "/vectors/fetch",
                    params=[
                        ("namespace", self.config.pinecone_namespace),
                        *[("ids", i) for i in ids],
                    ],
                )
                if not set(ids).issubset(result.get("vectors", {})):
                    visible = False
                    break
            if visible:
                return
            await asyncio.sleep(1)
        raise ProviderError("Pinecone vectors are not visible yet; retry indexing")

    async def query(self, vector, generations):
        vector_literal(vector, self.config.embedding_dimensions)
        if not generations:
            return []
        body = await self.data(
            "/query",
            {
                "vector": vector,
                "topK": 6,
                "includeValues": False,
                "filter": {
                    "$and": [
                        {"embedding_signature": {"$eq": self.config.embedding_signature}},
                        {
                            "$or": [
                                {
                                    "$and": [
                                        {"document_id": {"$eq": str(doc)}},
                                        {"generation": {"$eq": str(generation)}},
                                    ]
                                }
                                for doc, generation in generations
                            ]
                        },
                    ]
                },
            },
        )
        try:
            return [int(m["id"]) for m in body["matches"]]
        except (KeyError, TypeError, ValueError):
            raise ProviderError("Pinecone returned invalid search results") from None

    async def delete_generation(self, document_id, generation):
        if generation:
            await self.data(
                "/vectors/delete",
                {
                    "filter": {
                        "$and": [
                            {"document_id": {"$eq": str(document_id)}},
                            {"generation": {"$eq": str(generation)}},
                        ]
                    }
                },
            )


def vector_record(chunk_id, document_id, generation, vector, signature):
    return {
        "id": str(chunk_id),
        "values": vector,
        "metadata": {
            "document_id": str(document_id),
            "generation": str(generation),
            "embedding_signature": signature,
        },
    }
