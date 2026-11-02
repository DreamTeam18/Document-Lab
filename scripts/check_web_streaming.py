"""Browser regression: render tokens before completion and replace the final draft.

Run: uv run --with playwright python -m scripts.check_web_streaming
Uses a controllable mock SSE stream; no database writes or model credits.
"""

import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:3001"


def main():
    checks = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            headless=True,
        )
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route(
            "**/api/rag/documents",
            lambda route: route.fulfill(
                json=[
                    {
                        "id": "11111111-1111-4111-8111-111111111111",
                        "title": "Streaming test manual",
                        "edition": "test",
                    }
                ]
            ),
        )
        # A route.fulfill body is buffered. A controlled ReadableStream lets us
        # assert on rendered output while the response is deliberately still open.
        page.add_init_script("""(() => {
            const original = window.fetch.bind(window);
            window.fetch = async (input, options) => {
                if (String(input) !== '/api/rag/query') return original(input, options);
                const encoder = new TextEncoder();
                const body = new ReadableStream({start(controller) {
                    window.sendTestEvent = (event, data) => controller.enqueue(
                        encoder.encode(`event: ${event}\\ndata: ${JSON.stringify(data)}\\n\\n`));
                    window.closeTestStream = () => controller.close();
                }});
                return new Response(body, {headers: {'Content-Type': 'text/event-stream'}});
            };
        })();""")
        page.goto(BASE + "/workspace/chats/new", wait_until="networkidle")
        page.get_by_role("checkbox").check()
        page.get_by_role("textbox", name="Message", exact=True).fill("Explain the label rule.")
        page.get_by_role("button", name="Send", exact=True).click()
        page.wait_for_function("typeof window.sendTestEvent === 'function'")

        def send(event, data):
            page.evaluate("([event,data]) => window.sendTestEvent(event,data)", [event, data])

        send("session", {"thread_id": "22222222-2222-4222-8222-222222222222"})
        send("token", {"delta": "Streaming draft"})
        expect(page.get_by_text("Streaming draft", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Stop", exact=True)).to_be_visible()
        checks.append("First delta is visible before result or stream closure")
        send("token", {"delta": " arrives incrementally."})
        expect(
            page.get_by_text("Streaming draft arrives incrementally.", exact=True)
        ).to_be_visible()
        checks.append("Second delta appends to the existing answer")
        send(
            "result",
            {
                "answer": "**Validated answer** replaces the draft. [1]",
                "citations": [
                    {
                        "citation": 1,
                        "document_id": "11111111-1111-4111-8111-111111111111",
                        "document_title": "Streaming test manual",
                        "edition": "test",
                        "kind": "section",
                        "number": "1",
                        "page": 3,
                    }
                ],
            },
        )
        page.evaluate("window.closeTestStream()")
        expect(
            page.get_by_text("Streaming draft arrives incrementally.", exact=True)
        ).to_have_count(0)
        expect(page.get_by_text("Validated answer", exact=True)).to_have_count(1)
        checks.append("Validated final answer replaces provisional text without duplication")
        page.get_by_text("[1] Streaming test manual · Page 3", exact=True).click()
        expect(page.get_by_role("button", name="Stop", exact=True)).to_have_count(0)
        checks.append("Final citations are interactive and streaming controls settle")
        assert not errors, errors
        checks.append("No browser runtime errors")
        Path(".local").mkdir(exist_ok=True)
        page.screenshot(path=".local/web-streaming.png")
        browser.close()
    Path(".local/web-streaming-results.json").write_text(json.dumps(checks, indent=2))
    for check in checks:
        print("PASS:", check)


if __name__ == "__main__":
    main()
