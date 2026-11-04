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
  -> LangGraph: triage -> structured plan or direct retrieval -> assess -> optional refinement -> answer
       -> fixed conversational response for supported greetings/help
       -> bounded error-handler recovery
       -> OpenRouter chat (default: openrouter/free)
       -> OpenRouter embeddings (same API key)
       -> Pinecone: semantic vector search
       -> PostgreSQL: exact section/table lookup, keyword fallback
       -> bounded parent/child/reference expansion
  -> atomic conversation save -> result with source citations

Local normalized JSON / sample graph export
  -> local ingestion -> embeddings -> PostgreSQL transaction
```

A successful first attempt uses at most four chat-generation calls and
MAX_SUB_QUESTIONS + 1 embedding calls (planned questions plus one refinement).
Recovery allows at most two extra stage attempts. Separate request-wide caps
(default six chat calls and thirteen embedding calls) count attempted calls,
including failures and streaming generation, before calling providers. All
attempts share the original deadline; answer generation is never replayed.
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

## Workflow agent organization

`app/workflow.py` assembles the graph; `app/agents/nodes.py` contains callable
planning, retrieval, assessment, refinement and answering agents. Dependencies
are injected through the provider/storage protocols in `app/agents/contracts.py`.
Each agent returns a typed state patch without mutating request state. The shared
search service retains the existing embedding-failure fallback. Agent failures
propagate to a graph boundary that routes them through the dedicated error handler;
cancellation always propagates to the caller.

The original node names, prompts, retrieval limits, citation handling and public SSE
event types are preserved. Graph edges now explicitly route failures for recovery. Conversation persistence remains in PostgreSQL; the graph
has no process-local checkpointer. Agent isolation and exception contracts are
covered by `uv run pytest -q tests/test_agents.py`.

## Workflow failure recovery

Every execution stage routes sanitized failures to `error_handler`. Transient
OpenRouter/Pinecone HTTP failures (408, 429, 500, 502, 503, 504) and network/timeouts
can retry triage, planning, retrieval, assessment or refinement. The entire request shares
two additional attempts with 0.25s/0.5s backoff and its original chat deadline.
Authentication/configuration errors, malformed provider responses, SQL failures
and unexpected internal failures terminate without retry. Malformed assessment
output is marked as an assessment error, with at most one refinement and
reassessment; it never silently marks evidence sufficient.
Malformed or non-transiently failed plans retain the original single-question
fallback; exhausted transient planner retries also fall back if time remains. Budget
or deadline exhaustion is terminal. Embedding failures
retain exact/full-text retrieval with a warning.

Answer generation is never replayed, even before the first token. Failed graphs
end with an explicit failed status, emit SSE `error`, and do not save a completed
turn or emit `result`. SQL version conflicts occur outside graph recovery and never
rerun generation. Cancellation propagates through nodes and backoff; closing a
provider connection does not guarantee every upstream provider stops billing.
Logs contain only stage, failure code and elapsed time, never provider bodies.

Run `uv run pytest -q tests/test_recovery.py tests/test_streaming.py tests/test_deep.py`
for failure routing, retry budgets, API persistence, cancellation and streaming
regressions. These tests mock external services and do not spend model credits.

## Entry routing

Requests enter `triage` before research. Exact greetings/thanks and basic help or
context-free ambiguous prompts return fixed conversational/clarification responses
with empty citations and no model or retrieval calls. Selected documents are still
required by the API and UI. These responses are saved as successful turns.

Simple explicit section/table lookups skip classification and planning. Other
questions use one bounded OpenRouter classification call with a locally validated
route/rewrite schema. Single factual lookups go to retrieval; complex requests go
to planning. Recent history is capped at 6,000 characters, used only to resolve
follow-ups. Original questions and selected document IDs remain unchanged.
Invalid classifications or rewrites that drop numeric references fall back to
planning. A model classification alone can never authorize an evidence-free answer.
No model reasoning or arbitrary direct response is sent to the client.

Routing saves calls for greetings and explicit lookups, but adds one call for
complex research; it is not a universal latency improvement. Direct conversational
responses emit progress and a final result without token events. Research answers
retain live token streaming. `tests/test_triage.py` covers routes, call counts,
unsafe classifications, history bounds, recovery and API persistence.

## Structured research plans

`MAX_SUB_QUESTIONS` defaults to 2 and accepts 1–4. Plans contain stable IDs,
standalone questions, objectives, dependencies and the server-selected document
scope. Local validation rejects unknown fields, missing references, duplicate IDs,
cycles, and oversized plans. Duplicate questions are merged and dependency IDs
remapped. IDs are assigned deterministically after dependency ordering. Invalid
plans fall back to a single original-question plan, never a truncated partial plan.

Retrieval runs independent questions concurrently in dependency order and retains results
by sub-question ID. Dependencies control retrieval order; they do not execute
calculations or dynamically substitute previous answers. Assessment judges each sub-question separately in a bounded batch call. Synthesis
uses those judgments to build a shared citation catalog with per-question coverage.

`CHAT_CALL_LIMIT` (default 6, range 1–12) and `EMBEDDING_CALL_LIMIT` (default 13,
range 1–24) apply across triage, planning, retrieval, refinement, generation and
recovery. Counts represent attempted provider calls, not tokens or billed cost.
Budget exhaustion emits an error and never saves a successful turn. Successful
SSE results include `plan_size` and `usage` (counts and configured limits); terminal
graph errors include usage. Concurrent requests have separate counters.

Planning tests use reviewed synthetic question shapes and deterministic responses;
these verify contracts and limits, not live model decomposition quality.
Run `uv run pytest -q tests/test_planning.py` for focused validation.

## Optional HyDE retrieval (experimental)

`HYDE_ENABLED=false` by default. Enable it in the backend environment and restart
to add a `hyde` node after structured planning. Direct retrieval routes and
section/table/chapter-reference plan items bypass hypothetical generation.
Each eligible planned question receives at most one JSON hypothetical passage,
limited to 300 output tokens and 2,000 characters. Generation is sequential,
within the plan size, shared call limits and request deadline.

Retrieval always searches the original question first. An optional second search
embeds the hypothetical passage with the same OpenRouter embedding model and
passes that vector to existing scoped storage/Pinecone search. The lookup text
remains the original question, so invented section numbers never drive exact
lookup. Existing document, active-generation and embedding-signature checks stay
in place. No reindexing or new database is required.

Original and additional real hits are deduplicated and interleaved, original hit
first, within the existing evidence limits. Hypothetical text is not citation
metadata or synthesis evidence, is not persisted, and is cleared after retrieval.
Provider failures or invalid hypothetical output retain ordinary retrieval.
Cancellation propagates. HyDE reserves two chat calls for assessment/answering
and embedding calls for remaining original questions plus refinement; under tight
budgets some hypothetical searches are skipped with a warning.

Each used hypothesis adds one chat and one embedding call, plus one search.
Tests compare the same deterministic fixture with HyDE disabled/enabled and verify
actual vector wiring, isolation and fallbacks. They do not establish semantic
quality or real-world latency benefit. Before changing the default, run both modes
on the same reviewed, held-out golden questions and compare retrieval recall,
answer support, latency and cost. That live quality evaluation remains pending.

## Concurrent research

`RESEARCH_CONCURRENCY=2` limits concurrent sub-question workers per request
(range 1–4). `RESEARCH_SERVICE_CONCURRENCY=2` limits active workers across API
requests in one backend process (range 1–8). Multiple server processes/instances
have separate limits; this is not a distributed provider rate limiter. Set the
request limit to 1 for sequential execution.

Ready questions execute in bounded dependency waves; a dependent question starts
after its prerequisites finish. Results retain plan order, sub-question IDs, source
hits, status, warnings and elapsed milliseconds, regardless of completion order.
Expected provider failures retain independent evidence and block dependent work.
If all work fails, normal bounded graph recovery applies. Unexpected errors,
budget exhaustion, disconnects and deadlines cancel and await outstanding workers.
Optional HyDE embeddings receive deterministic budget allocations before workers
start. No background work survives a cancelled retrieval node.

Pinecone requests no longer hold PostgreSQL connections while awaiting network I/O.
Generation IDs are revalidated and document rows share-locked before source
hydration; a concurrent reindex produces a conflict instead of using stale matches.
Tests use controlled async delays and mocked SQL/Pinecone boundaries; they do not
measure real provider throughput. Run `uv run pytest -q tests/test_concurrency.py`
for concurrency, ordering, partial failure, cancellation, cross-request isolation
and connection-release checks.


### Per-question assessment and final synthesis (#6 and #7)

Assessment returns sufficient, partial, none, or assessment_error for each planned
question. Supporting chunk IDs must belong to that question's presented evidence.
Partial judgments must identify gaps. Failed research remains explicit; malformed
judgments cannot authorize evidence. One targeted refinement and reassessment is
allowed when the request budget can still reserve answer generation.

The dedicated SynthesisAgent (also exposed as AnsweringAgent for compatibility)
uses only assessed supporting excerpts, deduplicated by document and chunk.
Each question receives an equal share of the 18,000-character evidence budget.
Its coverage packet links question IDs to global citation numbers, missing
information and context truncation. Editions and conflicting excerpts remain
distinct. HyDE passages and failed research are never treated as source evidence.

Only final synthesis streams real provider deltas. The final result replaces
provisional text after citation-reference validation; interrupted generation is
not replayed or saved. Citation validation checks reference membership, not
whether every claim is entailed by its source. Deterministic tests verify these
contracts; reviewed held-out live-model claim-support evaluation is still needed
before making answer-quality claims.

Run focused checks with:
```sh
uv run pytest -q tests/test_assessment.py tests/test_synthesis.py tests/test_streaming.py
```

## Automatic document + web research (#9)

Select documents and ask a question. After document retrieval, evidence assessment
and bounded refinement, validated partial or missing evidence triggers web search.
Sufficient evidence, greetings, clarification and invalid assessments do not trigger
external search. There is no checkbox or public-query input. The current question
(first 300 characters) is sent to Tavily; document excerpts, evaluator-generated
queries and conversation history are never sent. Web findings are external context,
not proof of internal policies. The composer explains this automatic behavior.

Set the optional server-side `TAVILY_KEY` in the local environment.
`TAVILY_INCLUDE_DOMAINS` accepts a JSON list of allowed publishers. Without a
key, document search works normally and the frontend shows web search as
unavailable. Clients can check `GET /health` for `web_available`.

The query API requires no web flags. Selected document IDs remain required. Tavily uses basic search, three results, no generated answer,
no automatic parameter escalation and no raw page content. Every HTTP attempt,
including a retry, consumes the same hard limit of two per request. Network
requests have a 12-second timeout inside the overall workflow deadline.
Results are capped at 128 KB and excerpts at 2,000 characters per result.

Web evidence is independently assessed for each public query. The final answer
uses **From your documents** and **From the web** sections, generated separately:
web excerpts never enter the document-answer prompt. Invalid assessments,
unavailable search or insufficient budgets produce explicit warnings while
retaining document evidence. Citation-ID validation does not establish factual
entailment. More precise query/claim-quality evaluation requires reviewed live
cases; automated mock tests validate routing and contracts, not semantic quality.

Web results are request-local and never indexed in Pinecone. To enforce the
non-persistence boundary, the saved answer retains only the separately generated
document answer and a notice that the web response and links were not retained.
Web excerpts, generated web answer text and web citations are excluded from SQL
and browser storage. URL strings are also removed from saved question/answer
text and document citation metadata. The live response still includes typed web
source cards. A refresh therefore loses the web section and its links; explicitly
search again to verify external information. Interrupted web drafts are excluded
from browser persistence and failed server generations are never saved.

For automatic web-fallback turns, the final SSE result includes `persisted_answer` and
`persisted_citations` alongside the live answer/citations. The frontend keeps
those safe representations separate and uses them only for local persistence.
Legacy clients should not persist live web responses.

Validation:
```sh
uv run pytest -q tests/test_web_search.py
npm --prefix web test
npm --prefix web run typecheck
uv run --with playwright python -m scripts.check_web_research
```
The browser regression uses mocked documents, health and SSE responses; it
requires the current frontend build on port 3001 and uses no provider credits.

## Research validation (#5 and #6)

The [recorded concurrency benchmark and live assessment evaluation](docs/validation/research-validation.md)
include methodology, fixed synthetic cases, measured results and limitations.
Run `uv run python -m scripts.validate_research` for the offline concurrency benchmark;
add `--live-assessment` to explicitly use the configured OpenRouter model for the
12-case assessment evaluation. The Builder.ai golden dataset remains separate work.
