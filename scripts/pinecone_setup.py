"""Validate/create the dedicated index and backfill existing vectors without re-embedding."""

import asyncio
import json
from uuid import uuid4

import httpx
import psycopg

from app.config import settings
from app.pinecone import PineconeVectors, vector_record
from app.providers import ProviderError


async def main():
    config = settings()
    async with httpx.AsyncClient(timeout=45) as client:
        vectors = PineconeVectors(config, client)
        listed = await vectors.request("GET", "https://api.pinecone.io/indexes")
        print("Pinecone authentication: passed")
        if config.pinecone_index not in [i["name"] for i in listed.get("indexes", [])]:
            await vectors.request(
                "POST",
                "https://api.pinecone.io/indexes",
                json={
                    "name": config.pinecone_index,
                    "dimension": config.embedding_dimensions,
                    "metric": "cosine",
                    "vector_type": "dense",
                    "spec": {"serverless": {"cloud": "aws", "region": "us-east-1"}},
                },
            )
        for _ in range(60):
            info = await vectors.request(
                "GET", "https://api.pinecone.io/indexes/" + config.pinecone_index
            )
            if info.get("status", {}).get("ready"):
                break
            await asyncio.sleep(2)
        await vectors.connect()
        print("Index ready: dimensions and cosine metric verified")
        async with await psycopg.AsyncConnection.connect(
            config.database_url.get_secret_value()
        ) as conn:
            cur = await conn.execute("SELECT id FROM rag.documents ORDER BY id")
            document_ids = [r[0] for r in await cur.fetchall()]
        total = 0
        for doc in document_ids:
            async with await psycopg.AsyncConnection.connect(
                config.database_url.get_secret_value()
            ) as conn:
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (str(doc),)
                )
                cur = await conn.execute(
                    "SELECT embedding_signature, vector_generation FROM rag.documents WHERE id=%s",
                    (doc,),
                )
                row = await cur.fetchone()
                if not row:
                    continue
                signature, old = row
                if signature != config.embedding_signature:
                    raise ProviderError(
                        "Existing document uses a different embedding model; re-ingest it first"
                    )
                generation = old or uuid4()
                cur = await conn.execute(
                    "SELECT id, embedding::text FROM rag.chunks WHERE document_id=%s ORDER BY id",
                    (doc,),
                )
                items = [
                    vector_record(r[0], doc, generation, json.loads(r[1]), signature)
                    for r in await cur.fetchall()
                ]
                await vectors.upsert(items)
                await vectors.wait_visible(items)
                await conn.execute(
                    "UPDATE rag.documents SET vector_generation=%s WHERE id=%s", (generation, doc)
                )
                total += len(items)
        print(
            f"Backfill complete: {len(document_ids)} documents, {total} vectors; no embedding calls"
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ProviderError as exc:
        raise SystemExit(str(exc)) from None
