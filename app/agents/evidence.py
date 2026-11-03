"""Existing JSON and citation handling shared by the workflow agents."""

import json
import re


def parse_object(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def prepare_evidence(hits, max_chars=18000):
    blocks, sources, used = [], [], 0
    for hit in hits:
        number = len(sources) + 1
        source = {
            key: str(hit[key]) if key == "document_id" else hit[key]
            for key in (
                "document_id",
                "section_id",
                "number",
                "title",
                "page",
                "document_title",
                "edition",
                "kind",
            )
        }
        source["citation"] = number
        block = f"[{number}] {json.dumps(source)}\n{hit['text'][:3000]}"
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        sources.append(source)
        used += len(block)
    return "\n\n".join(blocks), sources


def grounded_citations(answer, sources):
    # Some models emit full-width citation delimiters despite the prompt. Keep
    # the source ID validation, but normalize these equivalent numeric formats.
    answer = re.sub(r"【(\d+)】|［(\d+)］", lambda m: f"[{m[1] or m[2]}]", answer)
    if answer.strip() == "INSUFFICIENT_EVIDENCE":
        return "The selected documents do not contain enough evidence to answer this question.", []
    numbers = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
    valid = {s["citation"] for s in sources}
    # Do not return unsupported numbered citations as a seemingly grounded answer.
    if not numbers or not numbers.issubset(valid):
        return "I could not produce a supported answer with valid source citations.", []
    return answer, [s for s in sources if s["citation"] in numbers]
