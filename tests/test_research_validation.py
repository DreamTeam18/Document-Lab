import json

import pytest

from scripts.validate_research import CASES, assessment_state, benchmark, score


def test_reviewed_fixture_contract():
    cases = json.loads(CASES.read_text())
    assert len(cases) == len({c["id"] for c in cases}) == 12
    assert {c["expected_status"] for c in cases} == {"sufficient", "partial", "none"}
    for c in cases:
        assert c["review_rationale"].strip()
        assert set(c["expected_evidence_ids"]) <= set(range(1, len(c["excerpts"]) + 1))
        assert bool(c["expected_evidence_ids"]) == (c["expected_status"] != "none")
        state = assessment_state(c)
        assert all(h["document_id"] in state["document_ids"] for h in state["hits"])


def test_error_rates_have_separate_denominators_and_do_not_hide_errors():
    rows = [
        dict(expected="sufficient", actual="sufficient", evidence_match=True),
        dict(expected="sufficient", actual="partial", evidence_match=False),
        dict(expected="partial", actual="sufficient", evidence_match=False),
        dict(expected="none", actual="none", evidence_match=True),
        dict(expected="none", actual="ProviderError", evidence_match=False),
    ]
    result = score(rows)
    assert result["status_accuracy"]["rate"] == 2 / 5
    assert result["false_sufficient"]["count"] == 1
    assert result["false_sufficient"]["denominator"] == 3
    assert result["false_insufficient"]["rate"] == 1 / 2
    assert result["errors"] == 1
    assert result["evidence_set_accuracy"]["rate"] == 2 / 5


def test_empty_scores_are_not_reported_as_perfect():
    result = score([])
    assert result["status_accuracy"]["rate"] is None
    assert result["false_sufficient"]["rate"] is None
    assert result["false_insufficient"]["rate"] is None


async def test_benchmark_runs_identical_work_at_each_limit():
    results = await benchmark(repeats=2)
    assert set(results) == {"1", "2", "4"}
    for limit, row in results.items():
        assert row["observed_peaks"] == [int(limit)]
        assert row["runs"] == 2
        assert row["min_ms"] > 0
        assert row["min_ms"] <= row["median_ms"] <= row["max_ms"]
    # Deliberately do not gate CI on noisy wall-clock speedups.
    assert results["1"]["speedup"] == pytest.approx(1)
