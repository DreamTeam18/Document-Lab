# Agentic RAG clone

A focused backend reimplementation of `../Agentic_RAG-sample-project` using
FastAPI, LangGraph, PostgreSQL, Pinecone, and OpenRouter for chat and embeddings. The original sample
is untouched. No Redis, Neo4j, separate API gateway, Tavily, Cohere, scheduled
keep-alives, or local conversation files are required.

This is a local, single-owner test app with no app access token or login.
Anyone who can reach the server can access its documents, conversations, and query API.
The local server binds to `127.0.0.1`; OpenRouter credentials stay on the backend.

Pinecone is configured for local semantic retrieval. See [setup and migration](PINECONE.md).
PostgreSQL vector copies remain for rollback.

## Architecture

```text
HTTP client
  -> FastAPI POST /query (SSE progress + final answer)
  -> PostgreSQL: selected documents + last 0–4 exchanges, capped at 6,000 characters
  -> LangGraph: plan -> retrieve -> assess -> optional refinement -> answer
       -> OpenRouter chat (default: openrouter/free)
       -> OpenRouter embeddings (same API key)
       -> Pinecone: semantic vector search
       -> PostgreSQL: exact section/table lookup, keyword fallback
       -> bounded parent/child/reference expansion
  -> atomic conversation save -> result with source citations

Local normalized JSON / sample graph export
  -> local ingestion -> embeddings -> PostgreSQL transaction
```

There are at most three chat-generation calls and three embedding calls per
question (two planned searches plus one refinement). No autonomous retry loop.
Embedding outages fall back to full-text and exact lookup, with a warning in the
response. Empty evidence produces an abstention. Citation IDs are checked against
retrieved sources; this does not prove factual correctness of every claim.

## Local setup

Requires Python 3.11+ and local PostgreSQL with pgvector.
The backend and database run on this machine. `uv.lock` pins dependencies.

```sh
uv sync --python 3.12
cp .env.example .env
```

Set these privately in `.env` (never commit it):

- `DATABASE_URL`: local PostgreSQL connection string for `rag_clone` on
  `127.0.0.1:5432`. The configured private `.env` contains the generated password.
  For future Supabase hosting, use its pooler with `sslmode=require`; prepared
  statements are disabled for transaction-pooler compatibility.
- `OPENROUTER_API_KEY`: used for every generation and embedding call.

`OPENROUTER_MODEL=openrouter/free` uses OpenRouter's free-model router. It can
change the underlying model; pin an available `:free` model for repeatable evals.
Paid chat model names are rejected unless `ALLOW_PAID_MODELS=true`. No paid
fallback model is configured. Free-model availability and quotas are not guaranteed.

All model requests go through OpenRouter with the same `OPENROUTER_API_KEY`.
Embeddings default to `EMBEDDING_MODEL=openai/text-embedding-3-small`, requested
at 768 dimensions and normalized before storage/search. No direct provider key
or embedding-provider selector is needed.

**Embedding requests may incur OpenRouter charges**, even with free chat.
`ALLOW_PAID_MODELS` controls chat model selection only. Set your OpenRouter
account/key spending limits appropriately. Changing the embedding model requires
re-ingesting existing documents; the backend rejects embedding-signature mismatches.
No live model calls are made during tests or startup.

The local installation lives in `.local/postgres`, with the database cluster in
`.local/pgdata`. PostgreSQL listens only on `127.0.0.1` and uses password
authentication. `.local/` is ignored by Git. Application data lives in `rag_clone`;
integration tests use the separate `rag_clone_test` database. Keep the configured
`.env`; copying the example over it would discard the local connection password.

Start or stop the existing local cluster from this project directory:

```sh
.local/postgres/bin/pg_ctl -D .local/pgdata -l .local/postgres.log start
.local/postgres/bin/pg_ctl -D .local/pgdata status
.local/postgres/bin/pg_ctl -D .local/pgdata stop -m fast
```

This project-local binary installation was built for this Mac and is not committed.
On another machine, install PostgreSQL and pgvector natively, create a development
database, and set its connection string in `.env` before applying the migration.

Apply the schema, ingest the fictional demo, and start the server:

```sh
uv run python -m scripts.migrate
uv run python -m scripts.ingest examples/demo.json
uv run uvicorn server:app --reload
```

The migration uses a private `rag` schema and installs vector in `extensions`,
matching typical Supabase installations. If vector already exists in `public`,
relocate it with `ALTER EXTENSION vector SET SCHEMA extensions` after checking
other applications using that database. Do not run this against an unrelated database.

## Earlier static test frontend (retained for comparison)

The current React frontend is at `http://localhost:3001/` (see below).
The earlier static chat is at `http://localhost:8001/legacy/chat`. The backend serves a plain HTML/CSS/JS
landing page at `/` and chat workspace at `/chat`; no separate frontend build or package installation is required.
The design adapts the dark/gold landing and sidebar chat layout from `../frontend-sample`.
Documents load automatically when opening the workspace; the mobile menu opens the document sidebar.

Click **Refresh document list**, select up to five indexed documents, and ask
a question. No app token is required. Provider keys stay on the backend. The page shows
workflow progress, final answers, source metadata, and errors. Follow-ups reuse
the session; choose New chat to change documents. Reloading clears the local
view and session selection; saved conversations remain in PostgreSQL.

This is a private test interface, not a multi-user application. Answers render
as plain text. It does not provide a saved-conversation browser.
The page loads without model/database credentials, but real queries need backend
credentials and ingested documents. No mock answers are substituted.

## API

```sh
curl -N http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"user_query":"What must archive labels contain?", "document_ids":["d00d0000-0000-4000-8000-000000000001"]}'
```

- `GET /health`: unauthenticated process liveness, not database readiness.
- `GET /documents`: available document UUIDs, titles, editions.
- `POST /query`: question, selected document UUIDs, optional existing `thread_id`.
- `GET /conversations/{thread_id}/messages?before=123&limit=20`: paginated history;
  pass the oldest returned ID as `before` for the next page.

Use `fetch()` with a POST body and a streaming reader for a browser client;
native EventSource cannot POST. Events are `session`, `progress`, `result`, `error`.
Progress events report completed stages; final-answer tokens are not individually
streamed. Errors after streaming begins arrive as SSE events, not HTTP error status.

History is selected with SQL `LIMIT`, never fetched in full for a question. The
selected documents cannot change within a conversation. Completed question/answer
pairs save atomically; concurrent requests on the same thread use optimistic
version checks to avoid silently saving answers against stale history. A failed
first request can leave an empty conversation, which is safe to reuse.

## Bring over the sample corpus

The sample's ingestion documentation references `nodes_chunked.jsonl` and
`edges_chunked.csv`. These exported corpus files were not found in the supplied
sample. When available, convert them without connecting to Neo4j:

```sh
uv run python -m scripts.convert_graph path/to/nodes_chunked.jsonl \
  path/to/edges_chunked.csv data/document.json \
  --document-id YOUR-UUID --title 'Your document title' --edition 'Your edition'
uv run python -m scripts.ingest data/document.json
```

Create the output directory first. The converter preserves graph node identifiers,
hierarchy, tables, equations/descriptions, and REFERENCES edges. It accepts both
historical HAS_CHUNK directions and rejects missing nodes/cycles/multiple parents.
Inspect the normalized output before ingestion: some exports lack page numbers or
have equations under a different property name. The converter does not perform OCR.

Alternatively author JSON matching `examples/demo.json`. Section IDs are scoped
to a document. Tables/equations/diagrams are typed section records rather than a
second content table, keeping the schema small. Ingestion chunks long text and
embeds outside the database transaction, then atomically replaces just the selected
document's content. A provider failure leaves the existing index unchanged.
Re-running ingestion embeds all content again; incremental embedding reuse is not
implemented. For the first version, use a small corpus. Do not silently replace an
edition under the same UUID if historical citations must remain stable.

OCR, automated Supabase Storage upload, and hosted ingestion
workers are not included. `source_uri` can record an uploaded file location.

## Deploy backend on Vercel

1. Create a Supabase project, obtain its PostgreSQL connection URL, and apply the
   migration locally. Keep the `rag` schema out of PostgREST's exposed schemas.
2. Ingest documents locally using the same embedding configuration as deployment.
3. Set the Vercel project root to this directory. `server.py` exposes FastAPI `app`.
4. Configure the secrets above in Vercel environment settings; never upload `.env`.
5. Deploy with the Python runtime and Fluid Compute. `vercel.json` sets 300 seconds;
   the application deadline defaults to 220 seconds. Dependency size/build and
   external connectivity still need verification on an actual Vercel deployment.

Connections are capped at three per warm instance; instances can multiply that
total, so use the provider's pooler. No always-on process or writable local disk
is used for persistence. Exact vector search avoids a memory-heavy ANN index for
the initial small corpus. Measure query latency and storage before scaling.

Free hosting/model/database quotas are independent. Vercel Hobby is for personal,
noncommercial use. This implementation does not add a distributed daily quota
counter; keep this unauthenticated demo private and set provider-side spend limits.

## Verification

Performance scenarios and measured results are in [PERFORMANCE_REPORT.md](PERFORMANCE_REPORT.md).
Run `uv run python -m scripts.performance_suite` for the local API/database cases;
add `--allow-live` for nine real OpenRouter questions. The suite uses a separate
`rag_clone_test` database by default, cleans its fixtures, and retains live demo
conversations in the app database. Its local latency budgets are provisional.

See [TEST_REPORT.md](TEST_REPORT.md) for the latest detailed results and limitations.
The optional `uv run python -m scripts.live_smoke --allow-live` check exercises the
running app with real OpenRouter calls and requires the demo document to be indexed.

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
node --test tests/frontend.test.mjs
```

Optional real database integration test: set `TEST_DATABASE_URL` in your shell
to the local `rag_clone_test` connection string (same credentials as `DATABASE_URL`,
with `/rag_clone_test` as the database name).
Use a disposable test database only; this test applies the schema and writes fixtures.

```sh
uv run pytest -q tests/test_database.py
```

Unit/API tests mock inference; integration tests use deterministic fake vectors
and real PostgreSQL. Neither spends model credits. Semantic retrieval quality,
actual provider access, source-corpus parity, and Vercel deployment require live
configuration and evaluation before claiming equivalence to the original sample.

Provider references:
[OpenRouter free models](https://openrouter.ai/docs/guides/routing/model-variants/free),
[OpenRouter embeddings](https://openrouter.ai/docs/api/api-reference/embeddings/submit-an-embedding-request).


## Upload a document locally

Click **Upload document** to open the system file picker. Select a text-based PDF,
UTF-8 TXT, or Markdown file. The app extracts text, creates OpenRouter embeddings,
and saves the document atomically in PostgreSQL. Once indexed, the list refreshes
and the new document is selected in a fresh chat. Original files are not saved.
PDF citations preserve page numbers; extracted text does not reconstruct table or
section hierarchy. Scanned PDFs and encrypted PDFs are rejected; OCR is not included.
Limits: 10 MB, 100 PDF pages, 1,000,000 extracted characters, 600 chunks.
Uploads use the configured OpenRouter key and may incur embedding charges.
The HTTP endpoint is `POST /documents/upload?filename=manual.pdf` with raw file bytes
as the request body. Local upload indexing has a separate 30-minute deadline (`UPLOAD_TIMEOUT_SECONDS=1800`);
chat keeps its existing deadline. Keep the page open until indexing finishes.
This longer synchronous upload is for local use; hosted function deadlines still apply.

## React frontend (current interface)

The current landing page and workspace use the actual Next.js/React components
adapted from `frontend-sample`, including its OGL WebGL hero, dynamic examples,
interactive feature cards, Radix sidebar, themes, and Markdown chat rendering.

```sh
cd web
npm ci
npm run build
npm start
```

Open http://localhost:3001. Keep the FastAPI backend on port 8001 running.
`npm run dev` runs a development frontend instead. The Next.js server proxies
only the app endpoints to `RAG_BACKEND_URL` (default `http://127.0.0.1:8001`).
FastAPI `/` and `/chat` redirect to the frontend (`WEB_FRONTEND_URL` overrides its
address). The earlier static UI is retained at `/legacy` and `/legacy/chat`.
Recent conversations have a local browser display cache; completed turns also
remain saved in PostgreSQL. The landing examples are scripted, explicitly labeled
illustrations and do not call OpenRouter. See `web/IMPLEMENTATION.md` for the
source analysis, integration details, and limitations.

## Live answer streaming

`POST /query` emits SSE events in this order: `session`, retrieval `progress`,
zero or more `token` events (`{"delta":"answer fragment"}`), then `result`.
Only final answer generation streams; planning/assessment remain internal JSON calls.
Fragments come directly from OpenRouter `stream=true`, not a typing animation.
The frontend appends fragments immediately and replaces the draft with `result.answer`
when citation validation finishes, then attaches final citations. Draft text is provisional;
invalid citation output or insufficient-evidence output may be replaced at completion.

A successful completed answer is saved before the final result event. Interrupted,
failed, or cancelled generations are not saved as completed conversation turns.
Mid-stream failures emit `error`; the frontend marks the partial message as failed.
Stop aborts the browser request and the backend provider connection. No provider
reasoning tokens are forwarded. The existing request timeout still applies.

Frontend streaming browser regression (headless Chrome, mocked documents and a
controlled SSE stream; no provider usage):

```sh
uv run --with playwright python -m scripts.check_web_streaming
```

Requires the frontend on port 3001. Checks visible incremental output before stream
closure, final-answer replacement without duplication, citations, and settled controls.
Results and a screenshot are saved under `.local/web-streaming*`.
