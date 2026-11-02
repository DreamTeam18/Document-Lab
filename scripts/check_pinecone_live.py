"""Live OpenRouter -> Pinecone -> SQL retrieval check; removes its own fixture."""

import asyncio
from uuid import uuid4

import httpx
import psycopg

from app.config import settings
from app.models import Document
from app.pinecone import PineconeVectors
from app.providers import Providers
from app.storage import Storage
from scripts.ingest import ingest


async def main():
    config = settings().model_copy(update={"vector_backend": "pinecone"})
    doc = Document(
        id=uuid4(),
        title="Pinecone migration test",
        edition="test",
        sections=[
            {
                "id": "1",
                "number": "1",
                "title": "Storage",
                "text": "The archive stores backup keys in a violet titanium locker.",
            },
            {
                "id": "2",
                "number": "2",
                "title": "Cafeteria",
                "text": "The cafeteria serves apple juice every Tuesday.",
            },
        ],
    )
    async with httpx.AsyncClient(timeout=45) as client:
        vectors = PineconeVectors(config, client)
        providers = Providers(config, client)
        store = Storage(config.database_url.get_secret_value(), vectors)
        await store.pool.open()
        try:
            assert await ingest(doc, config, providers) == 2
            vector = await providers.embed("Where are the spare access keys kept?")
            hits = await store.search("Where are the spare access keys kept?", [doc.id], vector)
            assert hits and hits[0]["section_id"] == "1"
            assert all(h["document_id"] == doc.id for h in hits)
            # Replacement must publish a new generation and never return removed chunks.
            doc.sections[0].text = "The archive now stores backup keys in a green steel cabinet."
            assert await ingest(doc, config, providers) == 2
            hits = await store.search("Where are the spare access keys kept?", [doc.id], vector)
            assert hits and "green steel cabinet" in hits[0]["text"]
            assert all("violet" not in h["text"] for h in hits)
            assert await store.search("spare access keys", [uuid4()], vector) == []
            print("PASS: real embeddings, upload, semantic ranking, source isolation, replacement")
        finally:
            async with await psycopg.AsyncConnection.connect(
                config.database_url.get_secret_value()
            ) as conn:
                cur = await conn.execute(
                    "SELECT vector_generation FROM rag.documents WHERE id=%s", (doc.id,)
                )
                row = await cur.fetchone()
                if row:
                    await vectors.delete_generation(doc.id, row[0])
                await conn.execute("DELETE FROM rag.documents WHERE id=%s", (doc.id,))
            await store.pool.close()
            print("Temporary test document removed")


if __name__ == "__main__":
    asyncio.run(main())
