import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents.budget import BudgetExceeded, CallBudget, current_budget
from app.agents.web import WebResearchAgent
from app.api import app, storage
from app.config import settings
from app.models import Query
from app.privacy import WEB_NOT_RETAINED, safe_turn
from app.providers import ProviderError
from app.web_search import TavilySearch, bounded_search, safe_url
from app.workflow import Workflow
from tests.test_core import FakeSearch, assessment_fixture, hit
from tests.test_providers_api import FakeStorage

URL = "https://example.org/reference"
EXCERPT = "Public reference says labels identify an object."


@pytest.fixture
def budget():
    value = CallBudget(8, 13)
    token = current_budget.set(value)
    yield value
    current_budget.reset(token)


def response():
    return {"results": [{"url": URL, "title": "Public reference", "content": EXCERPT}]}


class Provider:
    def __init__(self, invalid=False, fail_stream=False, sufficient=False):
        self.invalid, self.fail_stream = invalid, fail_stream
        self.sufficient = sufficient
        self.prompts = []

    async def chat(self, system, prompt, *args):
        self.prompts.append((system, prompt))
        if system.startswith("Classify"):
            return '{"route":"complex_research","rewritten_question":"What are labels?"}'
        if system.startswith("You plan"):
            return '{"sub_questions":[{"id":"q1","question":"What are labels?","objective":"Find evidence","dependencies":[]}]}'
        if system.startswith("Check"):
            return assessment_fixture(
                json.dumps({"sufficient": self.sufficient, "query": "label details"}), prompt
            )
        if system.startswith("Assess public"):
            if self.invalid:
                return '{"assessments":[{"id":"bad","status":"sufficient","evidence_ids":["forged"],"missing_information":[]}]}'
            return json.dumps(
                {
                    "assessments": [
                        {
                            "id": q["id"],
                            "status": "sufficient",
                            "evidence_ids": [h["id"] for h in q["evidence"]],
                            "missing_information": [],
                        }
                        for q in json.loads(prompt)["queries"]
                    ]
                }
            )
        if system.startswith("Answer the supplied public"):
            return "Public finding [2]."
        return "Document finding [1]."

    async def embed(self, text):
        return [1.0] * 768

    async def stream_chat(self, system, prompt, *args):
        if self.fail_stream and system.startswith("Answer the supplied public"):
            yield "Partial external output"
            raise ProviderError("Web synthesis interrupted")
        yield await self.chat(system, prompt)


def initial(web=True):
    return {
        "question": "What are labels?",
        "history": "PRIVATE HISTORY",
        "document_ids": [uuid4()],
        "web_requested": web,
        "web_queries": ["Public label definition"] if web else [],
    }


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://user:pass@example.org",
        "http://localhost/a",
        "http://127.0.0.1/",
        "http://10.1.2.3/",
        "https://example.org/\nattack",
        "https://example.org:bad",
        "https://example.org\\@evil.test",
    ],
)
def test_invalid_urls(url):
    assert safe_url(url) is None


def test_normalize_url():
    assert safe_url("https://EXAMPLE.org:443/reference#section") == URL


def test_request_needs_no_web_controls():
    request = Query(user_query="Question", document_ids=[uuid4()])
    assert set(request.model_dump()) == {"user_query", "document_ids", "thread_id"}


async def test_payload_privacy_filters_and_dedup(budget):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "results": [
                    *response()["results"],
                    *response()["results"],
                    {"url": "javascript:alert(1)", "content": "bad"},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        hits = await TavilySearch("test", client, ["example.org"]).search("public query")
    assert len(hits) == 1
    assert hits[0]["source_type"] == "web"
    assert sent[0] == {
        "query": "public query",
        "search_depth": "basic",
        "include_answer": False,
        "auto_parameters": False,
        "max_results": 3,
        "include_raw_content": False,
        "include_domains": ["example.org"],
    }
    assert budget.web_calls == 1


async def test_concurrent_budget_ceiling(budget):
    sent = []

    async def handler(request):
        sent.append(request)
        await asyncio.sleep(0.01)
        return httpx.Response(200, json=response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        search = TavilySearch("test", client)
        results = await asyncio.gather(
            *(search.search(str(i)) for i in range(4)), return_exceptions=True
        )
    assert len(sent) == budget.web_calls == 2
    assert sum(isinstance(r, BudgetExceeded) for r in results) == 2


async def test_retries_share_two_attempts(budget):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(429, text="secret"))
    ) as client:
        search = TavilySearch("test", client)
        with pytest.raises(ProviderError, match="unavailable"):
            await bounded_search(search, "query")
        with pytest.raises(BudgetExceeded):
            await search.search("second query")
    assert budget.web_calls == 2


async def test_auth_failure_not_retried_and_sanitized(budget, caplog):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, text=URL))
    ) as client:
        with pytest.raises(ProviderError) as error:
            await bounded_search(TavilySearch("test", client), "query")
    assert budget.web_calls == 1
    assert URL not in str(error.value) + caplog.text


@pytest.mark.parametrize("payload", [{}, {"results": None}, {"results": "bad"}])
async def test_malformed_response(budget, payload):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(ProviderError):
            await TavilySearch("test", client).search("query")


async def test_oversized_response_rejected(budget):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="x" * 128001))
    ) as client:
        with pytest.raises(ProviderError, match="limit"):
            await TavilySearch("test", client).search("query")


async def test_cancel_does_not_retry(budget):
    entered = asyncio.Event()

    async def handler(request):
        entered.set()
        await asyncio.sleep(30)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        task = asyncio.create_task(bounded_search(TavilySearch("test", client), "query"))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert budget.web_calls == 1


@pytest.mark.parametrize("enabled", [False, True])
async def test_graph_coverage_gate_and_separate_evidence(enabled):
    queries = []

    def handler(request):
        queries.append(json.loads(request.content)["query"])
        return httpx.Response(200, json=response())

    provider = Provider(sufficient=not enabled)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        workflow = Workflow(provider, FakeSearch([hit()]), web_client=TavilySearch("test", client))
        result = await workflow.graph.ainvoke(initial(enabled))
    assert result["status"] == "succeeded"
    assert queries == (["What are labels?"] if enabled else [])
    if enabled:
        assert "## From your documents" in result["answer"]
        assert "## From the web" in result["answer"]
        assert [c["citation"] for c in result["citations"]] == [1, 2]
        assert result["citations"][1]["url"] == URL
        for system, prompt in provider.prompts:
            if system.startswith("Answer only"):
                assert EXCERPT not in prompt
            if system.startswith("Assess public") or system.startswith(
                "Answer the supplied public"
            ):
                assert "PRIVATE HISTORY" not in prompt
                assert "Labels must be blue" not in prompt
        assert result["usage"]["web_calls"] == 1


async def test_assessment_invalid_retains_documents():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=response()))
    ) as client:
        result = await Workflow(
            Provider(invalid=True), FakeSearch([hit()]), web_client=TavilySearch("test", client)
        ).graph.ainvoke(initial())
    assert result["status"] == "succeeded"
    assert "Document finding" in result["answer"]
    assert all(c.get("source_type") != "web" for c in result["citations"])
    assert any("invalid" in w for w in result["warnings"])


async def test_missing_provider_preserves_document_answer():
    result = await Workflow(
        Provider(), FakeSearch([hit()]), web_client=TavilySearch("", None)
    ).graph.ainvoke(initial())
    assert result["status"] == "succeeded"
    assert "unavailable" in " ".join(result["warnings"])


async def test_web_reserves_synthesis_budget(budget):
    budget.chat_calls = 6

    class Client:
        available = True

        async def search(self, query):
            raise AssertionError("Must not dispatch")

    result = await WebResearchAgent(Client(), Provider())(initial())
    assert result["web_results"] == []
    assert "budget" in " ".join(result["warnings"])


def test_persistence_never_retains_web_text_or_urls():
    citations = [
        {"source_type": "document", "citation": 1, "document_title": "Manual"},
        {"source_type": "web", "citation": 2, "url": URL, "text": EXCERPT},
    ]
    before = json.dumps(citations)
    q, a, c = safe_turn("Question " + URL, "Web text " + EXCERPT + URL, citations, "Doc [1] " + URL)
    assert URL not in json.dumps([q, a, c])
    assert EXCERPT not in a
    assert WEB_NOT_RETAINED in a
    assert len(c) == 1
    assert json.dumps(citations) == before


@pytest.mark.parametrize("fail", [False, True])
def test_api_live_payload_and_safe_persistence(monkeypatch, fail):
    monkeypatch.setenv("DATABASE_URL", "")
    settings.cache_clear()

    class Store(FakeStorage):
        async def search(self, *args):
            return [{**hit(), "document_id": args[1][0]}]

    store = Store()
    app.dependency_overrides[storage] = lambda: store
    try:
        with TestClient(app) as client:
            # A dedicated HTTP mock keeps all requests offline.
            transport = httpx.MockTransport(lambda r: httpx.Response(200, json=response()))
            web_http = httpx.AsyncClient(transport=transport)
            app.state.web_search = TavilySearch("test", web_http)
            app.state.providers = Provider(fail_stream=fail)
            result = client.post(
                "/query",
                json={
                    "user_query": "What are labels?",
                    "document_ids": [str(uuid4())],
                },
            )
            if fail:
                assert "event: error" in result.text
                assert "event: result" not in result.text
                assert not store.saved
            else:
                assert URL in result.text
                assert "persisted_answer" in result.text
                assert len(store.saved) == 1
                assert URL not in json.dumps(store.saved, default=str)
                assert EXCERPT not in json.dumps(store.saved, default=str)
                assert WEB_NOT_RETAINED in store.saved[0][3]
    finally:
        app.dependency_overrides.clear()
        settings.cache_clear()


@pytest.mark.parametrize(
    "scenario", ["empty", "invalid_assessment", "refinement_success", "greeting"]
)
async def test_automatic_fallback_routes(scenario):
    queries = []

    class ScenarioProvider(Provider):
        checks = 0

        async def chat(self, system, prompt, *args):
            if system.startswith("Check"):
                self.checks += 1
                if scenario == "invalid_assessment":
                    return "invalid JSON"
                if scenario == "refinement_success":
                    self.sufficient = self.checks > 1
            if system.startswith("Answer the supplied public"):
                number = json.loads(prompt)["evidence"].split("]")[0] + "]"
                return "Public finding " + number
            return await super().chat(system, prompt, *args)

    def handler(request):
        queries.append(json.loads(request.content)["query"])
        return httpx.Response(200, json=response())

    provider = ScenarioProvider()
    state = initial(False)
    if scenario == "greeting":
        state["question"] = "hello"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await Workflow(
            provider,
            FakeSearch([] if scenario == "empty" else [hit()]),
            web_client=TavilySearch("test", client),
            chat_call_limit=8,
        ).graph.ainvoke(state)
    assert result["status"] == "succeeded"
    if scenario == "empty":
        assert queries == ["What are labels?"]
        assert "## From your documents" in result["answer"]
        assert "## From the web" in result["answer"]
        assert all(c["source_type"] == "web" for c in result["citations"])
    else:
        assert queries == []
        assert not result.get("web_requested")
    if scenario == "refinement_success":
        assert provider.checks == 2
        assert result["refinement_attempts"] == 1
