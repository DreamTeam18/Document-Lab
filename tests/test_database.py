"""Opt-in real pgvector checks. Never connects to DATABASE_URL automatically."""

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app.config import Settings
from app.models import Document
from app.storage import Conflict, NotFound, Storage
from scripts.ingest import ingest


class Embeddings:
    async def embed(self, text, **kwargs):
        return [1.0] + [0.0] * 767


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not configured")
async def test_pgvector_ingestion_retrieval_history_and_isolation():
    dsn = os.environ["TEST_DATABASE_URL"]
    config = Settings(_env_file=None, database_url=dsn)
    schema = (Path(__file__).parents[1] / "migrations/001_initial.sql").read_text()
    async with await psycopg.AsyncConnection.connect(dsn, prepare_threshold=None) as conn:
        await conn.execute(schema)
    doc = Document(
        id=uuid4(),
        title="Integration fixture",
        edition="v1",
        sections=[
            {"id": "1", "number": "1", "text": "Archive records", "title": "Records"},
            {
                "id": "1.1",
                "number": "1.1",
                "text": "Archive labels must be blue.",
                "parent_id": "1",
                "references": ["1"],
            },
        ],
    )
    store = Storage(dsn)
    await store.pool.open()
    thread = None
    other = doc.model_copy(update={"id": uuid4(), "title": "Other corpus"})
    try:
        assert await ingest(doc, config, Embeddings()) == 2
        assert await ingest(other, config, Embeddings()) == 2
        # Re-ingestion is atomic and does not accumulate duplicate chunks.
        assert await ingest(doc, config, Embeddings()) == 2
        # A transaction failure after deleting old sections must restore the old corpus.
        broken = doc.model_copy(
            update={"sections": [doc.sections[0].model_copy(update={"parent_id": "missing"})]}
        )
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            await ingest(broken, config, Embeddings())
        hits = await store.search("Section 1.1", [doc.id], [1.0] + [0.0] * 767)
        assert hits[0]["section_id"] == "1.1"
        assert all(h["document_id"] == doc.id for h in hits)
        assert {h["section_id"] for h in hits} == {"1", "1.1"}
        lexical = await store.search("blue", [doc.id], None)
        assert lexical[0]["section_id"] == "1.1"
        assert await store.search("Section 1.1", [uuid4()], [1.0] + [0.0] * 767) == []
        with pytest.raises(Conflict):
            await store.conversation(None, [doc.id], "wrong-model", 8)
        with pytest.raises(NotFound):
            await store.conversation(None, [uuid4()], config.embedding_signature, 8)
        thread, version, history = await store.conversation(
            None, [doc.id], config.embedding_signature, 8
        )
        assert version == 0 and history == []
        with pytest.raises(Conflict):
            await store.conversation(thread, [other.id], config.embedding_signature, 8)
        for i in range(6):
            await store.save_turn(thread, i, f"question-{i}", f"answer-{i}", [])
        _, version, history = await store.conversation(
            thread, [doc.id], config.embedding_signature, 4
        )
        assert version == 6 and len(history) == 4
        assert history[0]["content"] == "question-4"
        with pytest.raises(Conflict):
            await store.save_turn(thread, 0, "stale question", "stale answer", [])
        page = await store.history(thread, 2**63 - 1, 3)
        older = await store.history(thread, page[0]["id"], 3)
        assert len(page) == len(older) == 3
        assert older[-1]["id"] < page[0]["id"]
        # Concurrent requests based on one version must not both persist.
        outcomes = await asyncio.gather(
            store.save_turn(thread, 6, "concurrent-a", "answer-a", []),
            store.save_turn(thread, 6, "concurrent-b", "answer-b", []),
            return_exceptions=True,
        )
        assert sum(isinstance(outcome, Conflict) for outcome in outcomes) == 1
        assert sum(outcome is None for outcome in outcomes) == 1
        history = await store.history(thread, 2**63 - 1, 50)
        assert len(history) == 14
        reopened = Storage(dsn)
        await reopened.pool.open()
        try:
            assert len(await reopened.history(thread, 2**63 - 1, 50)) == 14
        finally:
            await reopened.pool.close()
        # SQL-looking input cannot escape the selected corpus or execute SQL.
        assert await store.search("'; DROP TABLE rag.documents; --", [uuid4()], None) == []
        assert any(d["id"] == doc.id for d in await store.documents())
        assert (await store.conversation(thread, [doc.id], config.embedding_signature, 0))[2] == []
    finally:
        async with await psycopg.AsyncConnection.connect(dsn) as conn:
            if thread:
                await conn.execute("DELETE FROM rag.conversations WHERE id=%s", (thread,))
            await conn.execute("DELETE FROM rag.documents WHERE id=%s", (doc.id,))
            await conn.execute("DELETE FROM rag.documents WHERE id=%s", (other.id,))
        await store.pool.close()
