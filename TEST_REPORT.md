# Application test report

Tested locally on 2026-10-30 against PostgreSQL/pgvector and the running FastAPI
server at `http://127.0.0.1:8001`. The sample repository was not changed.

## Results

| Layer | Result | Coverage |
|---|---|---|
| Python suite | 52 passed, including real database integration | Authentication, request validation, provider errors, workflow bounds, citations, persistence |
| JavaScript streaming tests | 2 passed | Byte-by-byte UTF-8 and CRLF fragmentation, multiple events, unterminated final frame |
| Real database | Passed | Re-ingestion, rollback after a database constraint failure, vector/full-text retrieval, cross-document isolation, hierarchy expansion, pagination, history limits, concurrent writes, reopening connections |
| Chrome browser | Passed | Real authentication/document loading; simulated stream failures and document limits; retry state; new chat; safe HTML rendering; 390/768/1280px layouts |
| Live OpenRouter | 3 questions passed | Factual answer, conversational follow-up, missing evidence |
| Static checks | Passed | Ruff lint and formatting |

The database suite uses `rag_clone_test` and deletes its own fixtures. Browser
error cases intercept responses intentionally; they do not simulate successful
live inference. Provider failure tests use mocked HTTP responses and no credits.

## Bugs found and fixed

1. **Malformed embedding envelopes bypassed fallback.** Null, non-object, and
   malformed data entries could raise raw Python exceptions. They now produce
   sanitized `ProviderError` exceptions, allowing keyword/exact-search fallback.
2. **Overflowing embedding normalization.** Very large finite components could
   yield an infinite norm and normalize to all zeros. Invalid norms are rejected.
3. **Live answers rejected for citation typography.** The configured model emitted
   `【1】` despite the prompt requesting `[1]`. Equivalent numeric delimiters are
   normalized; unknown source IDs are still rejected. The initial live factual and
   follow-up tests failed before this correction, then passed after restarting.
4. **Missing-evidence answers were indistinguishable from citation-format failures.**
   Added an explicit insufficient-evidence response protocol and user-facing message.

## Live results after fixes

| Question | Observed result | Time |
|---|---|---|
| What must archive labels contain? | Document title and edition, citation to section 1.1 | 8.29 s |
| What color should they be? | Blue, citation to section 1.1 | 25.67 s |
| Required fire resistance rating for an archive room? | Explicitly insufficient evidence; no fabricated rating | 9.18 s |

All six messages were persisted and returned by the history API. This uses the
fictional two-chunk demo, not an actual building-code corpus. Live calls used the
configured OpenRouter key and may incur charges. Test conversations are retained;
their IDs and full demo results are in ignored `.local/live-test-results.json`.

## Reproduce

```sh
# Use a dedicated test database, not the app database.
# Set TEST_DATABASE_URL privately to the rag_clone_test connection string.
uv run pytest -q
node --test tests/frontend.test.mjs
uv run ruff check .
uv run ruff format --check .

# Explicit live inference; app must already be running and demo ingested.
uv run python -m scripts.live_smoke --allow-live
```

Without `TEST_DATABASE_URL`, pytest skips the real database case. The live smoke
script checks answer terms, valid document citations, abstention, and history;
these checks do not establish factual quality for arbitrary documents.

## Remaining limits

- This is a single-owner test app; shared-token holders can access all documents.
- No high-concurrency load test, Vercel deployment validation, or large-corpus
  relevance benchmark was performed.
- Citation ID validation does not prove that every sentence follows from its source.
- Model outputs and latency vary. The 25.67-second follow-up shows that the UI must
  continue to handle long-running requests.
- PDF parsing/upload, a saved-conversation browser, and automated ingestion jobs
  remain outside the implemented scope.
