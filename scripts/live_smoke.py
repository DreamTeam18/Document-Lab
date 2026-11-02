"""Explicit live demo check. Uses configured OpenRouter credits; keeps a test conversation."""

import argparse
import json
import time
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--allow-live", action="store_true", required=True)
    args = parser.parse_args()
    document = "d00d0000-0000-4000-8000-000000000001"
    cases = [
        ("factual", "What must archive labels contain?", ("title", "edition")),
        ("follow_up", "What color should they be?", ("blue",)),
        (
            "missing_evidence",
            "What is the required fire resistance rating in hours for an archive room?",
            (),
        ),
    ]
    report, thread = [], None
    with httpx.Client(timeout=240) as client:
        for name, question, expected in cases:
            started = time.monotonic()
            response = client.post(
                args.base_url + "/query",
                json={
                    "user_query": question,
                    "document_ids": [document],
                    "thread_id": thread,
                },
            )
            events = []
            for frame in response.text.split("\n\n"):
                lines = frame.splitlines()
                kind = next((line[7:] for line in lines if line.startswith("event: ")), None)
                raw = next((line[6:] for line in lines if line.startswith("data: ")), None)
                if raw:
                    data = json.loads(raw)
                    events.append((kind, data))
                    if kind == "session":
                        thread = data["thread_id"]
            result = next((value for key, value in events if key == "result"), {})
            answer = result.get("answer", "").lower()
            citations = result.get("citations", [])
            passed = response.is_success and bool(result)
            if expected:
                passed = passed and all(word in answer for word in expected) and bool(citations)
                passed = passed and all(cite["document_id"] == document for cite in citations)
            else:
                passed = passed and "do not contain enough evidence" in answer and not citations
            row = {
                "case": name,
                "passed": bool(passed),
                "seconds": round(time.monotonic() - started, 2),
                "result": result,
                "errors": [v for k, v in events if k == "error"],
            }
            report.append(row)
            print(json.dumps(row), flush=True)
        if thread:
            response = client.get(f"{args.base_url}/conversations/{thread}/messages")
            passed = response.is_success and len(response.json()) == 6
            report.append({"case": "persisted_six_messages", "passed": passed})
    output = Path(".local/live-test-results.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    raise SystemExit(0 if all(row["passed"] for row in report) else 1)


if __name__ == "__main__":
    main()
