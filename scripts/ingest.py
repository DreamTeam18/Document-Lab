"""Ingest a normalized document JSON atomically. Re-running replaces that document only."""

import argparse
import asyncio
import json
import logging
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg

from app.config import settings
from app.models import Document
from app.pinecone import PineconeVectors, vector_record
from app.providers import Providers, vector_literal


def chunks(text, size=2400, overlap=240):
    if size <= overlap or overlap < 0:
        raise ValueError("Chunk size must be greater than nonnegative overlap")
    start = 0
    while start < len(text):
        yield text[start : start + size]
        if start + size >= len(text):
            break
        start += size - overlap


async def ingest(document, config, providers):
    # Model calls happen before the transaction, so provider failures cannot leave
    # a half-indexed document and no DB connection is held during network inference.
    vectors = (
        PineconeVectors(config, providers.client) if config.vector_backend == "pinecone" else None
    )
    generation = uuid4() if vectors else None
    old_generation = None
    records = []
    for section in document.sections:
        for index, text in enumerate(chunks(section.text)):
            embedded_text = (
                f"{document.title} ({document.edition})\n{section.number} {section.title}\n{text}"
            )
            vector = await providers.embed(embedded_text)
            records.append(
                (document.id, section.id, index, section.page, text, vector_literal(vector))
            )
    async with await psycopg.AsyncConnection.connect(
        config.database_url.get_secret_value(), prepare_threshold=None
    ) as conn:
        # Serialize replacement of a given document, including concurrent first ingests.
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (str(document.id),)
        )
        if vectors:
            cur = await conn.execute(
                "SELECT vector_generation FROM rag.documents WHERE id=%s", (document.id,)
            )
            old = await cur.fetchone()
            old_generation = old[0] if old else None
        await conn.execute(
            "INSERT INTO rag.documents(id, title, edition, source_uri, embedding_signature) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET title=excluded.title, "
            "edition=excluded.edition, source_uri=excluded.source_uri, "
            "embedding_signature=excluded.embedding_signature",
            (
                document.id,
                document.title,
                document.edition,
                document.source_uri,
                config.embedding_signature,
            ),
        )
        await conn.execute("DELETE FROM rag.sections WHERE document_id=%s", (document.id,))
        async with conn.cursor() as cur:
            await cur.executemany(
                "INSERT INTO rag.sections(document_id,id,number,title,kind,parent_id) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                [
                    (document.id, s.id, s.number, s.title, s.kind, s.parent_id)
                    for s in document.sections
                ],
            )
            await cur.executemany(
                "INSERT INTO rag.section_references(document_id,source_id,target_id) VALUES (%s,%s,%s)",
                [(document.id, s.id, ref) for s in document.sections for ref in set(s.references)],
            )
            await cur.executemany(
                "INSERT INTO rag.chunks(document_id,section_id,chunk_index,page,text,embedding) "
                "VALUES (%s,%s,%s,%s,%s,%s::extensions.vector)",
                records,
            )
        if vectors:
            cur = await conn.execute(
                "SELECT id, embedding::text FROM rag.chunks WHERE document_id=%s ORDER BY id",
                (document.id,),
            )
            items = [
                vector_record(
                    row[0], document.id, generation, json.loads(row[1]), config.embedding_signature
                )
                for row in await cur.fetchall()
            ]
            await vectors.upsert(items)
            await vectors.wait_visible(items)
        await conn.execute(
            "UPDATE rag.documents SET vector_generation=%s WHERE id=%s", (generation, document.id)
        )
    # Cleanup is after SQL commit. Failed/partial generations cannot match SQL's active generation.
    if vectors and old_generation:
        try:
            await vectors.delete_generation(document.id, old_generation)
        except Exception:
            logging.getLogger(__name__).warning("Old Pinecone generation cleanup deferred")
    return len(records)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    args = parser.parse_args()
    document = Document.model_validate_json(args.document.read_text())
    config = settings()
    if not config.database_url.get_secret_value():
        raise SystemExit("Set DATABASE_URL before ingestion")
    async with httpx.AsyncClient(timeout=45) as client:
        count = await ingest(document, config, Providers(config, client))
    print(f"Indexed {count} chunks for document {document.id}")


if __name__ == "__main__":
    asyncio.run(main())
