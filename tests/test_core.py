from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.models import Document
from app.providers import ProviderError, vector_literal
from app.storage import explicit_numbers, recent_context
from app.workflow import Workflow, grounded_citations, prepare_evidence
from scripts.convert_graph import convert
from scripts.ingest import chunks


def hit(id=1):
    return {
        "id": id,
        "document_id": uuid4(),
        "section_id": "1.1",
        "number": "1.1",
        "title": "Labels",
        "page": 1,
        "document_title": "Demo",
        "edition": "v1",
        "kind": "section",
        "text": "Labels must be blue.",
    }


def test_embedding_dimensions_from_environment(monkeypatch):
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "768")
    assert Settings(_env_file=None).embedding_dimensions == 768
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "1536")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_paid_models_require_opt_in():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, openrouter_model="paid/model")
    assert Settings(_env_file=None).openrouter_model == "openrouter/free"


def test_history_budget_and_order():
    messages = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "new"}]
    assert recent_context(messages, 14) == "assistant: new"
    assert recent_context(messages, 0) == ""
    assert recent_context(messages, 100) == "user: old\nassistant: new"


def test_references_and_invalid_vectors():
    assert explicit_numbers("Section 1607.1 and Table 1607.1; chapter 16") == ["1607.1", "16"]
    with pytest.raises(ProviderError):
        vector_literal([1.0])
    with pytest.raises(ProviderError):
        vector_literal([float("nan")] * 768)


def test_chunking_preserves_tail_without_duplicate_last_chunk():
    assert list(chunks("abcdefghij", size=6, overlap=2)) == ["abcdef", "efghij"]
    with pytest.raises(ValueError):
        list(chunks("abc", size=2, overlap=2))


def test_document_rejects_cycles():
    with pytest.raises(ValidationError):
        Document(
            id=uuid4(),
            title="x",
            edition="v1",
            sections=[
                {"id": "a", "number": "1", "text": "x", "parent_id": "b"},
                {"id": "b", "number": "2", "text": "y", "parent_id": "a"},
            ],
        )


def test_citation_validation_and_budget():
    text, sources = prepare_evidence([hit()])
    assert "Labels must be blue" in text
    assert grounded_citations("Blue [1]", sources)[1] == sources
    assert grounded_citations("Blue [999]", sources)[1] == []
    assert grounded_citations("Unsupported", sources)[1] == []
    assert prepare_evidence([hit()], 1) == ("", [])


def test_graph_converter_preserves_table_and_reference():
    nodes = [
        {"uid": "s", "label": "Section", "properties": {"number": "1", "title": "Section"}},
        {"uid": "t", "label": "Table", "properties": {"table_id": "1.1", "rows": [["4", "m"]]}},
        {"uid": "p", "label": "Passage", "properties": {"text": "A passage"}},
    ]
    edges = [
        {"start_node_uid": "s", "end_node_uid": "t", "relationship_type": "CONTAINS"},
        {"start_node_uid": "p", "end_node_uid": "s", "relationship_type": "HAS_CHUNK"},
        {"start_node_uid": "p", "end_node_uid": "t", "relationship_type": "REFERENCES"},
    ]
    doc = convert(nodes, edges, uuid4(), "Demo", "v1")
    assert doc.sections[1].kind == "table"
    assert '"m"' in doc.sections[1].text
    assert doc.sections[2].parent_id == "s"
    assert doc.sections[2].references == ["t"]


class FakeProvider:
    def __init__(self, replies, fail_embedding=False):
        self.replies, self.calls = iter(replies), 0
        self.fail_embedding = fail_embedding

    async def chat(self, *args):
        if args[0].startswith("Classify document"):
            return '{"route":"complex_research","rewritten_question":"q"}'
        self.calls += 1
        return next(self.replies)

    async def embed(self, *args, **kwargs):
        if self.fail_embedding:
            raise ProviderError("unavailable")
        return [1.0] * 768


class FakeSearch:
    def __init__(self, hits):
        self.hits, self.calls = hits, []

    async def search(self, query, docs, embedding):
        self.calls.append((query, embedding))
        return self.hits


async def test_workflow_refines_once_and_falls_back_when_embeddings_fail():
    provider = FakeProvider(
        [
            '{"sub_questions":[{"id":"q1","question":"labels","objective":"Find supporting evidence","dependencies":[]}]}',
            '{"sufficient":false,"query":"label colors"}',
            "Labels must be blue [1].",
        ],
        fail_embedding=True,
    )
    store = FakeSearch([hit()])
    result = await Workflow(provider, store).graph.ainvoke(
        {"question": "What color?", "history": "", "document_ids": [uuid4()]}
    )
    assert len(store.calls) == 2
    assert all(embedding is None for _, embedding in store.calls)
    assert provider.calls == 3
    assert result["citations"][0]["citation"] == 1
    assert result["warnings"]


async def test_empty_retrieval_abstains_without_synthesis_call():
    provider = FakeProvider(["malformed plan", '{"sufficient":true}'])
    store = FakeSearch([])
    result = await Workflow(provider, store).graph.ainvoke(
        {"question": "missing", "history": "", "document_ids": [uuid4()]}
    )
    assert result["citations"] == []
    assert "could not find" in result["answer"]
    assert provider.calls == 2
