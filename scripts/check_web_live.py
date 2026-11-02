"""Explicit real upload and answer check through the React UI; uses OpenRouter credits."""

import argparse

import psycopg
from playwright.sync_api import sync_playwright

from app.config import settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-live", action="store_true", required=True)
    parser.parse_args()
    document_id = thread_id = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                headless=True,
            )
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto("http://127.0.0.1:3001/workspace/chats/new", wait_until="networkidle")
            with page.expect_file_chooser() as chooser:
                page.get_by_role("button", name="Upload document", exact=True).click()
            with page.expect_response(
                lambda r: "/documents/upload?" in r.url, timeout=180000
            ) as pending:
                chooser.value.set_files(
                    {
                        "name": "Frontend verification.txt",
                        "mimeType": "text/plain",
                        "buffer": b"Archive labels must contain the document title and edition. All archive labels must be blue.",
                    }
                )
            response = pending.value
            assert response.status == 201
            document_id = response.json()["id"]
            page.locator("label").filter(has_text="Frontend verification.txt").locator(
                "input:checked"
            ).wait_for()
            page.get_by_role("textbox", name="Message", exact=True).fill(
                "What must archive labels contain?"
            )
            page.get_by_role("button", name="Send", exact=True).click()
            page.locator('[aria-label="Sources"]').wait_for(timeout=240000)
            text = page.locator("body").inner_text().lower()
            assert "title" in text and "edition" in text
            threads = page.evaluate('JSON.parse(localStorage.getItem("document-lab.threads"))')
            thread_id = threads[0]["serverThreadId"]
            page.screenshot(path=".local/web-real-answer.png", full_page=True)
            print(
                "PASS: native file picker → proxy → OpenRouter embedding → PostgreSQL → selected source → real answer and citations"
            )
            browser.close()
        with psycopg.connect(settings().database_url.get_secret_value()) as conn:
            count = conn.execute(
                "SELECT count(*) FROM rag.messages WHERE conversation_id=%s", (thread_id,)
            ).fetchone()[0]
            assert count == 2
            print("PASS: both real conversation messages persisted in PostgreSQL")
    finally:
        if document_id:
            with psycopg.connect(settings().database_url.get_secret_value()) as conn:
                conn.execute(
                    "DELETE FROM rag.conversations WHERE %s = ANY(document_ids)", (document_id,)
                )
                conn.execute("DELETE FROM rag.documents WHERE id=%s", (document_id,))
            print("Cleaned up live test document and conversation")


if __name__ == "__main__":
    main()
