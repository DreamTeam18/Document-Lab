# Performance test results

Run: 2026-10-30T17:07:37.998052+00:00

**26/26 scenarios passed correctness and latency budgets.**

Budgets are provisional local-demo targets declared before the run, not production SLAs. Each timed operation includes its functional assertions. p95 uses nearest rank; for three samples it equals the maximum and is not a statistically stable tail estimate. No warm-up samples were discarded. HTTP uses pooled connections to the already-running local server.

| Scenario | Samples | p50 ms | p95 ms | Budget ms | Errors | Result |
|---|---:|---:|---:|---:|---:|---|
| HTTP health response | 20 | 1.31 | 1.87 | 250 | 0 | PASS |
| Frontend HTML delivery | 20 | 1.72 | 1.91 | 500 | 0 | PASS |
| Frontend JavaScript delivery | 20 | 1.72 | 1.83 | 500 | 0 | PASS |
| Authenticated document listing | 20 | 1.81 | 2.03 | 500 | 0 | PASS |
| Invalid token rejection | 20 | 1.18 | 1.24 | 250 | 0 | PASS |
| Blank question validation | 20 | 1.61 | 1.81 | 250 | 0 | PASS |
| Unknown document rejection | 20 | 1.98 | 2.25 | 500 | 0 | PASS |
| Unknown conversation rejection | 20 | 2.14 | 2.27 | 500 | 0 | PASS |
| 20 concurrent document requests | 10 | 63.67 | 70.2 | 2000 | 0 | PASS |
| Vector retrieval / 1,000 chunks | 20 | 75.62 | 84.81 | 500 | 0 | PASS |
| Keyword retrieval / 1,000 chunks | 20 | 1.55 | 1.92 | 500 | 0 | PASS |
| Exact section prioritization | 20 | 76.02 | 80.92 | 500 | 0 | PASS |
| Parent and cross-reference expansion | 20 | 2.33 | 2.48 | 500 | 0 | PASS |
| Cross-document retrieval isolation | 20 | 3.04 | 3.28 | 500 | 0 | PASS |
| No keyword match | 20 | 0.98 | 1.11 | 500 | 0 | PASS |
| 20 concurrent vector searches / pool size 3 | 10 | 637.73 | 675.17 | 3000 | 0 | PASS |
| 8-message context from 4,000 messages | 20 | 0.66 | 1.11 | 300 | 0 | PASS |
| Latest history page / 4,000 messages | 20 | 1.76 | 2.5 | 300 | 0 | PASS |
| Older history page / 4,000 messages | 20 | 1.8 | 1.92 | 300 | 0 | PASS |
| History disabled / 4,000 messages | 20 | 0.63 | 0.73 | 300 | 0 | PASS |
| Atomic question-answer save and readback | 20 | 1.89 | 2.18 | 500 | 0 | PASS |
| 10 same-version concurrent saves | 10 | 4.67 | 4.81 | 1500 | 0 | PASS |
| Atomic replacement of 1,000 chunks | 3 | 540.22 | 611.22 | 10000 | 0 | PASS |
| Live factual answer with citations | 3 | 5169.15 | 6924.89 | 60000 | 0 | PASS |
| Live conversational follow-up and persistence | 3 | 12464.05 | 15401.7 | 60000 | 0 | PASS |
| Live missing-evidence abstention | 3 | 14685.85 | 21405.15 | 60000 | 0 | PASS |

## Method and scope

- Database tests: 1,000 synthetic-vector chunks in one fixture document, 10 in another, and 4,000 history messages. Fixtures are deleted from rag_clone_test afterward.
- Synthetic vectors exercise database execution, filtering and concurrency, not semantic relevance or embedding-provider speed. Replacement timings exclude real embedding inference.
- HTTP validation/listing tests use the real app and its demo document. Concurrent batch latency measures the entire batch, not per-request p95.
- Live tests use the two-chunk fictional demo and real configured OpenRouter models. Nine live questions incur provider usage. Their conversations remain in the app database.
- Live first-event timing measures the session event, not the first answer token. Final answers are not token-streamed.
- Not a sustained stress test, cold-start benchmark, large real-corpus relevance evaluation, or hosted deployment benchmark.
- Machine/network/provider load can change these results. Live content checks verify expected terms and citation document IDs, not a full expert factual evaluation.

## Reproduce

```sh
uv run python -m scripts.performance_suite --allow-live
```

By default the suite derives rag_clone_test from DATABASE_URL; TEST_DATABASE_URL can override it. Use a dedicated test database. Omitting --allow-live runs only local scenarios. Raw results and batch throughput: .local/performance-results.json.

Live session-event p95: 5.67 ms.
