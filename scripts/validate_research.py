"""Reproducible synthetic concurrency benchmark and opt-in live evidence assessment.

uv run python -m scripts.validate_research
uv run python -m scripts.validate_research --live-assessment
No handbook text, database access or Tavily calls are used.
"""

import argparse
import asyncio
import copy
import hashlib
import json
import platform
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import httpx

from app.agents.assessment import AssessmentAgent
from app.agents.nodes import RetrievalAgent, SearchService
from app.config import Settings
from app.providers import Providers

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests/fixtures/assessment_cases.json"
DOC = UUID("11111111-1111-4111-8111-111111111111")


def hit(i, text):
    return dict(
        id=i,
        document_id=DOC,
        section_id=str(i),
        number=str(i),
        title="Synthetic policy",
        page=i,
        document_title="Synthetic evaluation fixture",
        edition="v1",
        kind="section",
        text=text,
    )


class Embeddings:
    async def embed(self, query):
        return [1.0] * 768


class Store:
    def __init__(self):
        self.active = self.peak = 0

    async def search(self, query, docs, embedding):
        assert docs == [DOC]
        i = int(query[1:])
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0.02 * (4 - i))
            return [hit(i + 1, "Labels must be blue.")]
        finally:
            self.active -= 1


async def benchmark(repeats=10):
    state = dict(
        document_ids=[DOC],
        warnings=[],
        searches=["q0"],
        research_plan=[
            dict(
                id=f"q{i}",
                question=f"q{i}",
                objective="Retrieve evidence",
                dependencies=[],
                document_ids=[DOC],
            )
            for i in range(4)
        ],
    )
    samples = {n: [] for n in (1, 2, 4)}
    peaks = {n: [] for n in samples}
    for repetition in range(repeats + 1):
        # Rotate ordering; first cycle is warmup and is excluded from timing statistics.
        order = [1, 2, 4]
        order = order[repetition % 3 :] + order[: repetition % 3]
        for limit in order:
            store = Store()
            original = copy.deepcopy(state)
            start = time.perf_counter()
            result = await RetrievalAgent(SearchService(Embeddings(), store), limit)(state)
            elapsed = (time.perf_counter() - start) * 1000
            assert state == original
            assert store.active == 0 and store.peak == limit
            assert [r["sub_question_id"] for r in result["research_results"]] == [
                "q0",
                "q1",
                "q2",
                "q3",
            ]
            assert [h["id"] for h in result["hits"]] == [1, 2, 3, 4]
            if repetition:
                samples[limit].append(elapsed)
                peaks[limit].append(store.peak)
    baseline = statistics.median(samples[1])
    return {
        str(n): dict(
            runs=repeats,
            median_ms=round(statistics.median(values), 3),
            min_ms=round(min(values), 3),
            max_ms=round(max(values), 3),
            speedup=round(baseline / statistics.median(values), 3),
            observed_peaks=sorted(set(peaks[n])),
        )
        for n, values in samples.items()
    }


def assessment_state(case):
    hits = [hit(i + 1, text) for i, text in enumerate(case["excerpts"])]
    return dict(
        question=case["question"],
        document_ids=[DOC],
        searches=[case["question"]],
        hits=hits,
        warnings=[],
        research_plan=[
            dict(
                id="q1",
                question=case["question"],
                objective="Assess source coverage",
                dependencies=[],
                document_ids=[DOC],
            )
        ],
        research_results=[dict(sub_question_id="q1", hits=hits, status="retrieved")],
    )


def score(rows):
    sufficient = [r for r in rows if r["expected"] == "sufficient"]
    insufficient = [r for r in rows if r["expected"] != "sufficient"]

    def rate(count, denominator):
        return dict(
            count=count, denominator=denominator, rate=count / denominator if denominator else None
        )

    return dict(
        status_accuracy=rate(sum(r["actual"] == r["expected"] for r in rows), len(rows)),
        false_sufficient=rate(
            sum(r["actual"] == "sufficient" for r in insufficient), len(insufficient)
        ),
        false_insufficient=rate(
            sum(r["actual"] in {"partial", "none"} for r in sufficient), len(sufficient)
        ),
        errors=sum(r["actual"] not in {"sufficient", "partial", "none"} for r in rows),
        evidence_set_accuracy=rate(sum(r["evidence_match"] for r in rows), len(rows)),
    )


async def evaluate():
    config = Settings()
    cases = json.loads(CASES.read_text())
    assert len({c["id"] for c in cases}) == len(cases)
    rows = []
    async with httpx.AsyncClient(timeout=45) as client:
        provider = Providers(config, client)
        for case in cases:
            start = time.perf_counter()
            try:
                async with asyncio.timeout(50):
                    result = await AssessmentAgent(provider)(assessment_state(case))
                judgment = result["assessments"][0]
                actual = judgment["status"]
                evidence_match = sorted(judgment["evidence_ids"]) == case["expected_evidence_ids"]
            except Exception as exc:
                actual, evidence_match = type(exc).__name__, False
            rows.append(
                dict(
                    id=case["id"],
                    expected=case["expected_status"],
                    actual=actual,
                    evidence_match=evidence_match,
                    seconds=round(time.perf_counter() - start, 3),
                )
            )
            print(case["id"], actual, flush=True)
    return dict(
        model=config.openrouter_model,
        temperature=0,
        cases=rows,
        metrics=score(rows),
        max_model_calls=len([c for c in cases if c["excerpts"]]),
        dataset_sha256=hashlib.sha256(CASES.read_bytes()).hexdigest(),
    )


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-assessment", action="store_true")
    parser.add_argument("--output", type=Path, default=Path(".local/research-validation.json"))
    args = parser.parse_args()
    report = dict(
        timestamp=datetime.now(timezone.utc).isoformat(),
        python=platform.python_version(),
        platform=platform.platform(),
        commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        working_tree_dirty=bool(
            subprocess.check_output(["git", "status", "--porcelain"], text=True)
        ),
        concurrency=await benchmark(),
    )
    if args.live_assessment:
        report["assessment"] = await evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report.get("assessment", {}).get("metrics", report["concurrency"]), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
