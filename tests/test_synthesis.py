"""Deterministic synthesis contracts; these are not live model quality scores."""

import json

import pytest

from app.agents.synthesis import SynthesisAgent, synthesis_evidence
from app.providers import ProviderError
from tests.test_core import hit


def state():
    a, b = hit(1), hit(2)
    return {
        "question": "Compare both requirements.",
        "history": "",
        "document_ids": [a["document_id"], b["document_id"]],
        "research_plan": [{"id": "q1", "question": "First?"}, {"id": "q2", "question": "Second?"}],
        "research_results": [
            {"sub_question_id": "q1", "status": "retrieved", "hits": [a]},
            {"sub_question_id": "q2", "status": "retrieved", "hits": [b]},
        ],
        "assessments": [
            {
                "sub_question_id": "q1",
                "status": "sufficient",
                "evidence_ids": [1],
                "missing_information": [],
            },
            {
                "sub_question_id": "q2",
                "status": "partial",
                "evidence_ids": [2],
                "missing_information": ["Exception unknown."],
            },
        ],
    }


def test_global_catalog_and_coverage():
    context, sources, coverage = synthesis_evidence(state())
    assert [s["citation"] for s in sources] == [1, 2]
    assert [c["citations"] for c in coverage] == [[1], [2]]
    assert coverage[1]["missing_information"] == ["Exception unknown."]
    assert "[1]" in context and "[2]" in context


def test_shared_chunk_has_one_citation():
    s = state()
    s["research_results"][1]["hits"] = s["research_results"][0]["hits"]
    s["assessments"][1]["evidence_ids"] = [1]
    _, sources, coverage = synthesis_evidence(s)
    assert len(sources) == 1
    assert [c["citations"] for c in coverage] == [[1], [1]]


def test_large_first_question_cannot_starve_second():
    s = state()
    a = s["research_results"][0]["hits"][0]
    s["research_results"][0]["hits"] = [{**a, "id": i, "text": "x" * 10000} for i in range(1, 13)]
    s["assessments"][0]["evidence_ids"] = list(range(1, 13))
    context, sources, coverage = synthesis_evidence(s, 4000)
    assert len(context) <= 4000
    assert coverage[0]["context_truncated"]
    assert coverage[1]["citations"]
    assert sources[-1]["document_id"] == str(s["document_ids"][1])


def test_conflicting_editions_preserved():
    s = state()
    s["research_results"][1]["hits"][0].update(edition="v2", text="Labels must be red.")
    context, sources, _ = synthesis_evidence(s)
    assert {source["edition"] for source in sources} == {"v1", "v2"}
    assert "blue" in context and "red" in context


@pytest.mark.parametrize("status", ["none", "assessment_error"])
def test_unassessed_evidence_excluded(status):
    s = state()
    s["assessments"][1]["status"] = status
    _, sources, coverage = synthesis_evidence(s)
    assert len(sources) == 1
    assert coverage[1]["citations"] == []
    assert coverage[1]["status"] == status


@pytest.mark.parametrize("status", ["failed", "blocked"])
def test_failed_research_cannot_become_evidence(status):
    s = state()
    s["research_results"][1]["status"] = status
    _, sources, coverage = synthesis_evidence(s)
    assert len(sources) == 1
    assert coverage[1]["citations"] == []


def test_foreign_document_rejected():
    s = state()
    s["document_ids"].pop()
    with pytest.raises(ProviderError):
        synthesis_evidence(s)


def test_hypothesis_and_unsupported_chunks_excluded():
    s = state()
    s["hyde_passages"] = {"q1": "Invented hypothetical statement"}
    s["research_results"][0]["hits"].append(hit(99))
    context, _, _ = synthesis_evidence(s)
    assert "Invented" not in context
    assert len(synthesis_evidence(s)[1]) == 2


def test_catalog_stable_when_result_order_changes():
    s = state()
    before = synthesis_evidence(s)
    s["research_results"].reverse()
    assert synthesis_evidence(s) == before


class Provider:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    async def chat(self, system, prompt):
        self.calls.append((system, json.loads(prompt)))
        return self.answer


async def test_synthesis_receives_original_question_and_gaps():
    provider = Provider("Blue [1], with an unknown exception [2].")
    result = await SynthesisAgent(provider)(state())
    assert len(result["citations"]) == 2
    system, prompt = provider.calls[0]
    assert prompt["question"] == "Compare both requirements."
    assert prompt["coverage"][1]["missing_information"]
    assert "untrusted" in system


@pytest.mark.parametrize("answer", ["Unsupported [99]", "No references", "INSUFFICIENT_EVIDENCE"])
async def test_invalid_or_abstaining_answers_do_not_claim_citations(answer):
    result = await SynthesisAgent(Provider(answer))(state())
    assert result["citations"] == []


async def test_no_supported_sources_skips_generation():
    s = state()
    s["assessments"] = []
    provider = Provider("must not be called")
    result = await SynthesisAgent(provider)(s)
    assert not provider.calls
    assert result["citations"] == []


async def test_real_deltas_forwarded_and_final_text_validated(monkeypatch):
    events = []
    monkeypatch.setattr("app.agents.synthesis.get_stream_writer", lambda: events.append)

    class Streaming(Provider):
        async def stream_chat(self, *args):
            for part in ["Draft ", "[99]"]:
                yield part

    result = await SynthesisAgent(Streaming(""), stream_answer=True)(state())
    assert events == [{"delta": "Draft "}, {"delta": "[99]"}]
    assert result["answer"] != "Draft [99]"
    assert result["citations"] == []


async def test_stream_failure_propagates_without_replay(monkeypatch):
    events = []
    monkeypatch.setattr("app.agents.synthesis.get_stream_writer", lambda: events.append)

    class Streaming(Provider):
        async def stream_chat(self, *args):
            yield "Draft"
            raise ProviderError("Stream failed")

    with pytest.raises(ProviderError):
        await SynthesisAgent(Streaming(""), stream_answer=True)(state())
    assert events == [{"delta": "Draft"}]
