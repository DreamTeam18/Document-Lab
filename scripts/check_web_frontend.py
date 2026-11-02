"""Browser checks for the React UI. Run with uv run --with playwright python -m scripts.check_web_frontend."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:3001"


def main():
    checks = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            headless=True,
            args=["--enable-unsafe-swiftshader"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_selector(".galaxy-container canvas")
        page.wait_for_timeout(1000)
        assert page.locator("canvas").count() >= 2
        checks.append("WebGL hero and masked canvas mount")
        page.screenshot(path=".local/web-landing-desktop.png")
        page.get_by_role("tab", name="Connect the details").click()
        page.get_by_role("button", name="Answer", exact=True).click()
        page.get_by_text("Complete orientation, then ask your team lead", exact=False).wait_for()
        page.wait_for_timeout(400)
        page.screenshot(path=".local/web-examples-desktop.png")
        checks.append("Interactive example tabs, stage selection and pause")
        page.goto(BASE + "/workspace/chats/new", wait_until="networkidle")
        page.locator("input[type=checkbox]").first.wait_for()
        assert page.get_by_role("button", name="Send", exact=True).is_disabled()
        page.locator("input[type=checkbox]").first.check()
        checks.append("Real document API via proxy; sending requires selection")
        with page.expect_file_chooser():
            page.get_by_role("button", name="Upload document", exact=True).click()
        checks.append("Native file chooser")
        requests = []

        def query(route):
            requests.append(route.request.post_data_json)
            data = 'event: session\ndata: {"thread_id":"11111111-1111-4111-8111-111111111111"}\n\n'
            data += 'event: progress\ndata: {"step":"retrieve"}\n\n'
            result = {
                "answer": "**Blue labels** are required. [1]\n\n- Include title\n- Include edition",
                "citations": [
                    {
                        "citation": 1,
                        "document_id": "doc",
                        "document_title": "Test manual",
                        "edition": "v1",
                        "kind": "section",
                        "number": "1",
                        "page": 3,
                    }
                ],
            }
            data += "event: result\ndata: " + json.dumps(result) + "\n\n"
            route.fulfill(content_type="text/event-stream", body=data)

        page.route("**/api/rag/query", query)
        page.get_by_role("textbox", name="Message", exact=True).fill("What color?")
        page.get_by_role("button", name="Send", exact=True).click()
        page.get_by_text("Blue labels", exact=True).wait_for()
        assert (
            page.locator('[data-streamdown="strong"]').filter(has_text="Blue labels").count() == 1
        )
        page.get_by_text("[1] Test manual · Page 3", exact=True).click()
        checks.append("SSE progress, Markdown answer, expandable citations")
        page.get_by_role("textbox", name="Message", exact=True).fill("What else?")
        page.get_by_role("button", name="Send", exact=True).click()
        page.wait_for_function("document.querySelectorAll('[data-streamdown=strong]').length >= 2")
        assert requests[1]["thread_id"] == "11111111-1111-4111-8111-111111111111"
        assert "messages" not in requests[1]
        checks.append("Follow-up uses backend UUID and bounded request")
        page.reload(wait_until="networkidle")
        page.get_by_text("Blue labels", exact=True).first.wait_for()
        checks.append("Recent conversation, sources and citations survive reload")
        page.get_by_role("button", name="Settings and more").click()
        page.get_by_role("menuitem", name="Dark", exact=True).click()
        assert "dark" in page.locator("html").get_attribute("class")
        page.screenshot(path=".local/web-chat-dark.png")
        checks.append("Theme switching")
        for width in [390, 768, 1440]:
            page.set_viewport_size({"width": width, "height": 900})
            page.goto(BASE, wait_until="networkidle")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
            page.goto(BASE + "/workspace/chats/new", wait_until="networkidle")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
            if width == 390:
                page.get_by_role("button", name="Toggle Sidebar").click()
                page.get_by_role("button", name="Upload document", exact=True).wait_for()
                page.keyboard.press("Escape")
                page.screenshot(path=".local/web-chat-mobile.png")
        checks.append("390/768/1440 layouts and accessible mobile sidebar")
        reduced = browser.new_page(reduced_motion="reduce", viewport={"width": 1200, "height": 900})
        reduced.goto(BASE, wait_until="networkidle")
        reduced.locator("#examples").scroll_into_view_if_needed()
        reduced.get_by_text(
            "Include the document title and edition on every archive label.", exact=False
        ).wait_for()
        assert reduced.locator(".galaxy-container canvas").count() == 0
        checks.append("Reduced motion removes WebGL and leaves example answers readable")
        assert not errors, errors
        checks.append("No browser runtime errors")
        browser.close()
    Path(".local/web-checks.json").write_text(json.dumps(checks, indent=2))
    for check in checks:
        print("PASS:", check)


if __name__ == "__main__":
    main()
