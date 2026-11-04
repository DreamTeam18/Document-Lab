"""The web result is transient; never persist its text, URLs or source payloads."""

import re

WEB_NOT_RETAINED = (
    "From the web: web response and source links not retained. Search again to verify."
)


def strip_urls(text):
    return re.sub(r"(?i)(?:https?://|www\.)[^\s<>\]\"']+", "[link not retained]", text)


def safe_turn(question, answer, citations, document_answer=None):
    # A web turn supplies a separately generated document answer. Never attempt
    # to infer the boundary by parsing model-generated markdown headings.
    if document_answer is not None:
        answer = "## From your documents\n\n" + document_answer + "\n\n" + WEB_NOT_RETAINED
    return (
        strip_urls(question),
        strip_urls(answer),
        [
            {
                key: strip_urls(value) if isinstance(value, str) else value
                for key, value in c.items()
                if key not in {"url", "text", "excerpt"}
            }
            for c in citations
            if c.get("source_type") != "web"
        ],
    )
