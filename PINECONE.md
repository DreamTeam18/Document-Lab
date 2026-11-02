# Pinecone retrieval

Configuration (server-side `.env`):

```dotenv
VECTOR_BACKEND=pinecone
PINECONE_KEY=your-key
PINECONE_INDEX=agentic-rag
PINECONE_NAMESPACE=rag-clone
```

OpenRouter generates 768-dimensional embeddings. Pinecone stores and searches them
in a cosine index. PostgreSQL stores authoritative text, citations, relationships,
and conversations. Each database/application must use a separate namespace.

## Setup and migration

```sh
uv run python -m scripts.migrate
uv run python -m scripts.pinecone_setup
```

Setup creates the dedicated AWS us-east-1 serverless index if absent and validates
its dimensions. It backfills existing vectors without embedding calls. Run this
before enabling Pinecone, then restart the backend. Never switch namespace without
backfilling it first. No existing index is deleted.

Uploads write vectors before publishing the active document generation in SQL.
Queries filter by document, generation and embedding model; SQL rechecks document
scope. Old generations are deleted after successful replacement. Failed or cancelled
writes may leave unreferenced vectors, but these cannot be searched by the app.
Fetch visibility is checked before commit; Pinecone query visibility can still lag
briefly because of eventual consistency. Remote writes hold a bounded SQL transaction.

Existing pgvector columns and vector copies remain for recovery and rollback with
`VECTOR_BACKEND=pgvector`. Pinecone mode does not execute pgvector similarity queries.
Removing the PostgreSQL extension is a separate migration. Pinecone outages surface
as errors; embedding outages retain the existing keyword fallback with a warning.

## Verification

```sh
uv run pytest -q
uv run python -m scripts.check_pinecone_live
```

The live check uses real OpenRouter embedding calls and Pinecone operations; it
cleans up its own fixture. It verifies ingestion, semantic ranking, source isolation,
and replacement. The unit tests use mocked Pinecone HTTP responses.

Initial local migration: 2 existing documents, 112 vectors; zero re-embedding calls.
Live smoke test passed. Backend suite: 75 passed, 1 optional DB test skipped.

Reference: [Pinecone vector API](https://docs.pinecone.io/reference/api/2025-10/data-plane/query).
