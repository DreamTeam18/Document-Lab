"""Local functional performance suite. Real model calls require --allow-live."""

import argparse
import asyncio
import json
import math
import os
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import httpx
import psycopg
from psycopg.types.json import Jsonb

from app.config import settings
from app.models import Document
from app.storage import Conflict, Storage
from scripts.ingest import ingest


class SyntheticEmbeddings:
    async def embed(self, text):
        return [1.0] + [0.0] * 767


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    config = settings()
    url = urlsplit(config.database_url.get_secret_value())
    test_dsn = os.environ.get("TEST_DATABASE_URL") or urlunsplit(
        url._replace(path="/rag_clone_test")
    )
    if test_dsn == config.database_url.get_secret_value():
        raise SystemExit("Test and application databases must differ")
    store = Storage(test_dsn)
    await store.pool.open()
    rows, created_threads = [], []
    run_id = uuid4()
    document_id, other_id = uuid4(), uuid4()
    vector = [1.0] + [0.0] * 767
    test_config = config.model_copy(
        update={"database_url": config.database_url.__class__(test_dsn)}
    )
    base = args.base_url
    demo = UUID("d00d0000-0000-4000-8000-000000000001")

    async def bench(name, kind, operation, n=20, budget_ms=1000, units=1):
        elapsed, failures = [], []
        for _ in range(n):
            start = time.perf_counter()
            try:
                await operation()
            except Exception as exc:
                # Never persist URLs, credentials, provider bodies, or traceback locals.
                failures.append(type(exc).__name__)
            elapsed.append((time.perf_counter() - start) * 1000)
        row = {
            "name": name,
            "kind": kind,
            "samples": n,
            "units_per_sample": units,
            "p50_ms": round(statistics.median(elapsed), 2),
            "p95_ms": round(percentile(elapsed, 0.95), 2),
            "max_ms": round(max(elapsed), 2),
            "budget_ms": budget_ms,
            "functional_failures": len(failures),
            "error_types": sorted(set(failures)),
            "observed_units_per_second": round(n * units / (sum(elapsed) / 1000), 2),
        }
        row["passed"] = not failures and row["p95_ms"] <= budget_ms
        rows.append(row)
        print(json.dumps(row), flush=True)

    async def new_thread():
        thread, _, _ = await store.conversation(None, [document_id], config.embedding_signature, 8)
        created_threads.append(thread)
        return thread

    try:
        async with await psycopg.AsyncConnection.connect(test_dsn) as conn:
            await conn.execute(Path("migrations/001_initial.sql").read_text())
        # 1,000 independent passages and a second document with identical vectors.
        sections = [
            {
                "id": str(i),
                "number": str(i),
                "title": f"Topic {i}",
                "text": f"Archive benchmark passage {i}. Labels require a title. "
                + ("uniquetermblue " if i == 500 else "ordinary text ") * 30,
                "parent_id": "0" if i == 500 else None,
                "references": ["999"] if i == 500 else [],
            }
            for i in range(1000)
        ]
        corpus = Document(
            id=document_id, title="Performance fixture", edition=str(run_id), sections=sections
        )
        await ingest(corpus, test_config, SyntheticEmbeddings())
        await ingest(
            corpus.model_copy(update={"id": other_id, "sections": corpus.sections[:10]}),
            test_config,
            SyntheticEmbeddings(),
        )
        history_thread = await new_thread()
        async with await psycopg.AsyncConnection.connect(test_dsn) as conn:
            async with conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO rag.messages(conversation_id,role,content,citations) VALUES (%s,%s,%s,%s)",
                    [
                        (
                            history_thread,
                            "user" if i % 2 == 0 else "assistant",
                            f"Historical message {i} " + "context " * 50,
                            Jsonb([]),
                        )
                        for i in range(4000)
                    ],
                )
        async with httpx.AsyncClient(
            timeout=240, limits=httpx.Limits(max_connections=30)
        ) as client:

            async def get(path, status=200):
                response = await client.get(base + path)
                assert response.status_code == status
                return response

            async def api_docs():
                response = await get("/documents")
                assert any(d["id"] == str(demo) for d in response.json())

            async def public_health():
                assert (await get("/health")).json()["status"] == "ok"

            async def frontend():
                assert "Document Lab" in (await get("/legacy")).text

            async def js():
                assert "readEvents" in (await get("/static/app.js")).text

            async def legacy_header():
                response = await client.get(
                    base + "/documents", headers={"Authorization": "Bearer invalid"}
                )
                assert response.status_code == 200

            async def invalid_question():
                response = await client.post(
                    base + "/query", json={"user_query": " ", "document_ids": [str(demo)]}
                )
                assert response.status_code == 422

            async def missing_document():
                response = await client.post(
                    base + "/query", json={"user_query": "q", "document_ids": [str(uuid4())]}
                )
                assert response.status_code == 404

            async def missing_thread():
                response = await client.post(
                    base + "/query",
                    json={
                        "user_query": "q",
                        "document_ids": [str(demo)],
                        "thread_id": str(uuid4()),
                    },
                )
                assert response.status_code == 404

            async def concurrent_documents():
                await asyncio.gather(*(api_docs() for _ in range(20)))

            await bench("HTTP health response", "real HTTP", public_health, budget_ms=250)
            await bench("Frontend HTML delivery", "real HTTP", frontend, budget_ms=500)
            await bench("Frontend JavaScript delivery", "real HTTP", js, budget_ms=500)
            await bench(
                "Document listing without credentials", "real HTTP + DB", api_docs, budget_ms=500
            )
            await bench(
                "Legacy header does not gate access", "real HTTP + DB", legacy_header, budget_ms=250
            )
            await bench("Blank question validation", "real HTTP", invalid_question, budget_ms=250)
            await bench(
                "Unknown document rejection", "real HTTP + DB", missing_document, budget_ms=500
            )
            await bench(
                "Unknown conversation rejection", "real HTTP + DB", missing_thread, budget_ms=500
            )
            await bench(
                "20 concurrent document requests",
                "real HTTP + DB batch",
                concurrent_documents,
                n=10,
                budget_ms=2000,
                units=20,
            )

            async def search(kind):
                if kind == "vector":
                    hits = await store.search("labels", [document_id], vector)
                    assert hits and all(h["document_id"] == document_id for h in hits)
                elif kind == "keyword":
                    hits = await store.search("uniquetermblue", [document_id], None)
                    assert hits[0]["section_id"] == "500"
                elif kind == "exact":
                    hits = await store.search("Section 500", [document_id], vector)
                    assert hits[0]["section_id"] == "500"
                elif kind == "expand":
                    hits = await store.search("Section 500", [document_id], None)
                    assert {"500", "0", "999"} <= {h["section_id"] for h in hits}
                elif kind == "isolation":
                    hits = await store.search("Section 500", [other_id], vector)
                    assert hits and all(h["document_id"] == other_id for h in hits)
                elif kind == "empty":
                    assert await store.search("unfindableword", [document_id], None) == []

            for label, kind in [
                ("Vector retrieval / 1,000 chunks", "vector"),
                ("Keyword retrieval / 1,000 chunks", "keyword"),
                ("Exact section prioritization", "exact"),
                ("Parent and cross-reference expansion", "expand"),
                ("Cross-document retrieval isolation", "isolation"),
                ("No keyword match", "empty"),
            ]:
                await bench(
                    label, "real DB; synthetic vectors", lambda k=kind: search(k), budget_ms=500
                )

            async def retrieval_load():
                await asyncio.gather(*(search("vector") for _ in range(20)))

            await bench(
                "20 concurrent vector searches / pool size 3",
                "real DB batch; synthetic vectors",
                retrieval_load,
                n=10,
                budget_ms=3000,
                units=20,
            )

            async def bounded_history():
                _, _, history = await store.conversation(
                    history_thread, [document_id], config.embedding_signature, 8
                )
                assert len(history) == 8 and history[-1]["content"].startswith(
                    "Historical message 3999 "
                )

            async def first_page():
                page = await store.history(history_thread, 2**63 - 1, 20)
                assert len(page) == 20

            oldest = (await store.history(history_thread, 2**63 - 1, 20))[0]["id"]

            async def older_page():
                page = await store.history(history_thread, oldest, 20)
                assert len(page) == 20 and page[-1]["id"] < oldest

            async def zero_history():
                assert (
                    await store.conversation(
                        history_thread, [document_id], config.embedding_signature, 0
                    )
                )[2] == []

            await bench(
                "8-message context from 4,000 messages", "real DB", bounded_history, budget_ms=300
            )
            await bench(
                "Latest history page / 4,000 messages", "real DB", first_page, budget_ms=300
            )
            await bench("Older history page / 4,000 messages", "real DB", older_page, budget_ms=300)
            await bench("History disabled / 4,000 messages", "real DB", zero_history, budget_ms=300)

            async def save_pair():
                thread = await new_thread()
                await store.save_turn(thread, 0, "question", "answer", [])
                assert len(await store.history(thread, 2**63 - 1, 20)) == 2

            async def concurrent_save():
                thread = await new_thread()
                result = await asyncio.gather(
                    *(store.save_turn(thread, 0, "q", "a", []) for _ in range(10)),
                    return_exceptions=True,
                )
                assert sum(r is None for r in result) == 1
                assert sum(isinstance(r, Conflict) for r in result) == 9
                assert len(await store.history(thread, 2**63 - 1, 20)) == 2

            await bench(
                "Atomic question-answer save and readback", "real DB", save_pair, budget_ms=500
            )
            await bench(
                "10 same-version concurrent saves",
                "real DB batch",
                concurrent_save,
                n=10,
                budget_ms=1500,
                units=10,
            )

            async def reindex():
                assert await ingest(corpus, test_config, SyntheticEmbeddings()) == 1000
                async with store.pool.connection() as conn:
                    cur = await conn.execute(
                        "SELECT count(*) AS n FROM rag.chunks WHERE document_id=%s", (document_id,)
                    )
                    assert (await cur.fetchone())["n"] == 1000

            await bench(
                "Atomic replacement of 1,000 chunks",
                "real DB; mock embedding generation",
                reindex,
                n=3,
                budget_ms=10000,
                units=1000,
            )

            if args.allow_live:
                first_event_times = []

                async def live(question, expected, thread=None):
                    start = time.perf_counter()
                    first = None
                    result = None
                    session = thread
                    events = []
                    async with client.stream(
                        "POST",
                        base + "/query",
                        json={
                            "user_query": question,
                            "document_ids": [str(demo)],
                            "thread_id": thread,
                        },
                    ) as response:
                        assert response.status_code == 200
                        event = ""
                        async for line in response.aiter_lines():
                            if line.startswith("event: "):
                                event = line[7:]
                            if line.startswith("data: "):
                                data = json.loads(line[6:])
                                events.append(event)
                                if first is None:
                                    first = (time.perf_counter() - start) * 1000
                                if event == "session":
                                    session = data["thread_id"]
                                if event == "error":
                                    raise AssertionError("Live SSE error")
                                if event == "result":
                                    result = data
                    first_event_times.append(first)
                    assert result and events.index("session") < events.index("result")
                    answer = result["answer"].lower()
                    if expected:
                        assert all(word in answer for word in expected)
                        assert result["citations"] and all(
                            c["document_id"] == str(demo) for c in result["citations"]
                        )
                    else:
                        assert (
                            "do not contain enough evidence" in answer and not result["citations"]
                        )
                    return session

                sessions = []

                async def factual():
                    sessions.append(
                        await live("What must archive labels contain?", ("title", "edition"))
                    )

                async def followup():
                    thread = sessions.pop(0)
                    await live("What color should they be?", ("blue",), thread)
                    response = await client.get(f"{base}/conversations/{thread}/messages")
                    assert response.status_code == 200 and len(response.json()) == 4

                async def missing():
                    await live(
                        "What fire resistance rating in hours is required for the archive room?", ()
                    )

                await bench(
                    "Live factual answer with citations",
                    "real OpenRouter + HTTP + DB",
                    factual,
                    n=3,
                    budget_ms=60000,
                )
                await bench(
                    "Live conversational follow-up and persistence",
                    "real OpenRouter + HTTP + DB",
                    followup,
                    n=3,
                    budget_ms=60000,
                )
                await bench(
                    "Live missing-evidence abstention",
                    "real OpenRouter + HTTP + DB",
                    missing,
                    n=3,
                    budget_ms=60000,
                )
                print(
                    "Live first SSE event p95 ms:",
                    round(percentile(first_event_times, 0.95), 2),
                    flush=True,
                )
            else:
                first_event_times = []
    finally:
        async with await psycopg.AsyncConnection.connect(test_dsn) as conn:
            if created_threads:
                await conn.execute(
                    "DELETE FROM rag.conversations WHERE id=ANY(%s)", (created_threads,)
                )
            await conn.execute(
                "DELETE FROM rag.documents WHERE id=ANY(%s)", ([document_id, other_id],)
            )
        await store.pool.close()

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "results": rows,
        "live_first_event_ms": first_event_times,
        "passed": sum(r["passed"] for r in rows),
        "total": len(rows),
    }
    Path(".local/performance-results.json").write_text(json.dumps(report, indent=2))
    lines = [
        "# Performance test results",
        "",
        f"Run: {report['timestamp']}",
        "",
        f"**{report['passed']}/{report['total']} scenarios passed correctness and latency budgets.**",
        "",
        "Budgets are provisional local-demo targets declared before the run, not production SLAs. "
        "Each timed operation includes its functional assertions. p95 uses nearest rank; for three "
        "samples it equals the maximum and is not a statistically stable tail estimate. No warm-up "
        "samples were discarded. HTTP uses pooled connections to the already-running local server.",
        "",
        "| Scenario | Samples | p50 ms | p95 ms | Budget ms | Errors | Result |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['name']} | {r['samples']} | {r['p50_ms']} | {r['p95_ms']} | {r['budget_ms']} | {r['functional_failures']} | {'PASS' if r['passed'] else 'FAIL'} |"
        )
    lines += [
        "",
        "## Method and scope",
        "",
        "- Database tests: 1,000 synthetic-vector chunks in one fixture document, 10 in another, and 4,000 history messages. Fixtures are deleted from rag_clone_test afterward.",
        "- Synthetic vectors exercise database execution, filtering and concurrency, not semantic relevance or embedding-provider speed. Replacement timings exclude real embedding inference.",
        "- HTTP validation/listing tests use the real app and its demo document. Concurrent batch latency measures the entire batch, not per-request p95.",
        "- Live tests use the two-chunk fictional demo and real configured OpenRouter models. Nine live questions incur provider usage. Their conversations remain in the app database.",
        "- Live first-event timing measures the session event, not the first answer token. Final answers are not token-streamed.",
        "- Not a sustained stress test, cold-start benchmark, large real-corpus relevance evaluation, or hosted deployment benchmark.",
        "- Machine/network/provider load can change these results. Live content checks verify expected terms and citation document IDs, not a full expert factual evaluation.",
        "",
        "## Reproduce",
        "",
        "```sh",
        "uv run python -m scripts.performance_suite --allow-live",
        "```",
        "",
        "By default the suite derives rag_clone_test from DATABASE_URL; TEST_DATABASE_URL can override it. "
        "Use a dedicated test database. Omitting --allow-live runs only local scenarios. "
        "Raw results and batch throughput: .local/performance-results.json.",
    ]
    if first_event_times:
        lines += ["", f"Live session-event p95: {percentile(first_event_times, 0.95):.2f} ms."]
    Path("PERFORMANCE_REPORT.md").write_text("\n".join(lines) + "\n")
    print(f"FINAL: {report['passed']}/{report['total']} passed", flush=True)
    raise SystemExit(0 if report["passed"] == report["total"] else 1)


if __name__ == "__main__":
    asyncio.run(main())
