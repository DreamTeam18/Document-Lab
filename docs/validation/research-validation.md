# Research concurrency and assessment validation (#5, #6)

Completed 2026-11-04 against application commit `c80592176a8f91d56626716958df67c47f9e25d0` with the accompanying evaluation script/fixtures uncommitted at execution time. No application behavior changed for this evaluation. The machine-readable report records the environment, dataset hash, model, case-level outcomes and timings.

## #5: identical-work concurrency benchmark

Run `uv run python -m scripts.validate_research` for an offline benchmark. It invokes the actual `RetrievalAgent` and `SearchService` with synthetic embeddings and delayed storage. Each run retrieves the same four independent questions with storage delays of 80, 60, 40 and 20 ms. One warmup cycle is discarded; ten measured cycles rotate execution order across limits 1, 2 and 4. Assertions verify source scope, result order/IDs, unchanged input state, worker cleanup and peak concurrency on every run.

| Concurrency | Runs | Median ms | Min–max ms | Speedup over sequential |
|---|---:|---:|---:|---:|
| 1 | 10 | 206.055 | 203.587–209.513 | 1.000× |
| 2 | 10 | 103.483 | 101.940–104.879 | 1.991× |
| 4 | 10 | 82.523 | 81.306–82.596 | 2.497× |

Observed peak workers matched each configured limit. This measures scheduling over controlled I/O waits, not hosted Pinecone throughput, real model latency or production tail latency. CI verifies benchmark invariants, not brittle timing thresholds. Existing concurrency tests separately cover dependencies, partial failures, cancellation and process-wide limits.

## #6: live evidence-assessment evaluation

Run `uv run python -m scripts.validate_research --live-assessment` to repeat both checks. This explicitly uses the configured OpenRouter key/model and may incur provider charges. Default execution is offline. It uses no handbook, SQL, Pinecone or Tavily requests. Outputs contain only case IDs, labels, counts, timing and configuration identifiers, not provider bodies or credentials.

`tests/fixtures/assessment_cases.json` contains 12 deliberately simple synthetic cases, authored and reviewed against their included excerpts before the live call. Each has a fixed expected status, evidence-ID set and rationale. The coding assistant performed this source/label review; there has been no independent human review. No labels or application prompts were changed after observing model outputs. This is a small diagnostic evaluation, not the independently reviewed Builder.ai golden dataset planned in #10/#11.

Coverage: explicit fact, paraphrase, qualification, combined excerpts, missing owner, unresolved contradiction, missing condition, missing date, irrelevant text, absent evidence, wrong geographic scope and retrieved prompt injection. There are four sufficient, four partial and four none cases.

Live model: `openai/gpt-oss-120b`, temperature 0, using the actual `AssessmentAgent` and `Providers`. Eleven nonempty cases each make one model request. The empty-evidence case is resolved deterministically without a provider call. All 12 pass through the real assessment validation and evidence-selection path; responses are not mocked.

| Metric | Result |
|---|---:|
| Exact coverage status | 12/12 |
| Expected evidence-ID set | 12/12 |
| False sufficient (predicted sufficient for partial/none) | 0/8 |
| False insufficient (predicted partial/none for sufficient) | 0/4 |
| Provider/parse/assessment errors | 0 |
| Model-judged nonempty cases matching expected status | 11/11 |

Errors count against overall status/evidence accuracy, are reported separately, and are not counted as a positive or negative model sufficiency decision. Rate denominators include all expected members of each class. Always inspect the error count alongside the rates. Empty populations report null, not perfect accuracy.

These results establish that this configured model handled the reviewed diagnostic cases on this run. They do not establish a population error rate, robust prompt-injection resistance, answer faithfulness or performance on the Builder.ai corpus. Model routing/version and provider variability can change results. No tuning or release threshold was inferred from the 12 cases; broader independently reviewed held-out evaluation remains #10/#11.

## Artifacts and verification

- Runner: `scripts/validate_research.py`
- Fixed cases/rationales: `tests/fixtures/assessment_cases.json`
- Report: `docs/validation/research-validation-2026-11-04.json`
- Runner/metric tests: `tests/test_research_validation.py`
- Existing behavior tests: `tests/test_concurrency.py`, `tests/test_assessment.py`

The focused validation suite passed 49 tests. The report's `working_tree_dirty` flag is intentional: these new evaluation artifacts were present but not committed when the run began. Reproduce with the published fixture hash and application baseline rather than assuming that flag denotes a clean release benchmark.
