import asyncio
import copy
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.agents.nodes import RetrievalAgent, SearchService
from app.providers import ProviderError
from app.storage import Conflict, Storage
from tests.test_core import hit


def state(dependencies=False):
    docs = [uuid4()]
    return {
        "document_ids": docs,
        "searches": ["q0"],
        "warnings": [],
        "research_plan": [
            {
                "id": f"q{i}",
                "question": f"q{i}",
                "objective": "Find evidence",
                "dependencies": ["q0"] if dependencies and i == 1 else [],
                "document_ids": docs,
            }
            for i in range(4)
        ],
    }


class Provider:
    async def embed(self, query):
        return [1.0] * 768


class DelayedStore:
    def __init__(self, delay=0.02, failure=None):
        self.active = self.peak = 0
        self.started = []
        self.finished = []
        self.delay = delay
        self.failure = failure or {}
        self.scopes = []

    async def search(self, query, docs, vector):
        self.started.append(query)
        self.scopes.append(list(docs))
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.delay * (4 - int(query[-1])))
            if query in self.failure:
                raise self.failure[query]
            record = hit(int(query[-1]) + 1)
            record["document_id"] = docs[0]
            return [record]
        finally:
            self.active -= 1
            self.finished.append(query)


@pytest.mark.parametrize("limit", [1, 2, 4])
async def test_concurrency_limit_and_deterministic_order(limit):
    store = DelayedStore()
    original = state()
    before = copy.deepcopy(original)
    result = await RetrievalAgent(SearchService(Provider(), store), limit)(original)
    assert store.peak == limit
    assert [r["sub_question_id"] for r in result["research_results"]] == ["q0", "q1", "q2", "q3"]
    assert [h["id"] for h in result["hits"]] == [1, 2, 3, 4]
    assert all(r["elapsed_ms"] >= 0 for r in result["research_results"])
    assert original == before
    assert all(scope == original["document_ids"] for scope in store.scopes)


async def test_dependent_question_starts_only_after_prerequisite_finishes():
    class Store(DelayedStore):
        async def search(self, query, *args):
            if query == "q1":
                assert "q0" in self.finished
            return await super().search(query, *args)

    store = Store()
    await RetrievalAgent(SearchService(Provider(), store), 2)(state(True))


async def test_partial_failure_blocks_dependents_and_retains_independent_sources():
    store = DelayedStore(failure={"q0": ProviderError("secret")})
    result = await RetrievalAgent(SearchService(Provider(), store), 2)(state(True))
    assert [r["status"] for r in result["research_results"]] == [
        "failed",
        "blocked",
        "retrieved",
        "retrieved",
    ]
    assert "q1" not in store.started
    assert [h["id"] for h in result["hits"]] == [3, 4]
    assert "secret" not in str(result)
    assert result["warnings"]


async def test_total_failure_preserves_provider_error_for_bounded_graph_recovery():
    error = ProviderError("temporary", retryable=True)
    store = DelayedStore(failure={f"q{i}": error for i in range(4)})
    with pytest.raises(ProviderError) as raised:
        await RetrievalAgent(SearchService(Provider(), store), 2)(state())
    assert raised.value is error
    assert store.active == 0


async def test_unexpected_failure_cancels_siblings_before_returning():
    store = DelayedStore(delay=0.05, failure={"q3": RuntimeError("defect")})
    with pytest.raises(RuntimeError):
        await RetrievalAgent(SearchService(Provider(), store), 4)(state())
    assert store.active == 0
    assert len(store.finished) == 4


async def test_cancellation_cleans_up_workers_and_waiting_tasks():
    store = DelayedStore(delay=10)
    task = asyncio.create_task(RetrievalAgent(SearchService(Provider(), store), 2)(state()))
    while store.active < 2:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert store.active == 0
    assert len(store.started) == 2


async def test_deadline_cancels_all_workers():
    store = DelayedStore(delay=10)
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.02):
            await RetrievalAgent(SearchService(Provider(), store), 2)(state())
    assert store.active == 0


async def test_service_limiter_caps_two_clients_without_mixing_scopes():
    store = DelayedStore()
    agent = RetrievalAgent(SearchService(Provider(), store), 4, asyncio.Semaphore(2))
    left, right = state(), state()
    results = await asyncio.gather(agent(left), agent(right))
    assert store.peak == 2
    for result, request in zip(results, [left, right]):
        assert all(h["document_id"] == request["document_ids"][0] for h in result["hits"])


async def test_service_permits_released_after_cancellation():
    limiter = asyncio.Semaphore(1)
    store = DelayedStore(delay=10)
    task = asyncio.create_task(
        RetrievalAgent(SearchService(Provider(), store), 2, limiter)(state())
    )
    while not store.active:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with asyncio.timeout(1):
        await limiter.acquire()
    limiter.release()


@pytest.mark.parametrize("limit", [0, 5])
def test_invalid_concurrency_rejected(limit):
    with pytest.raises(ValueError):
        RetrievalAgent(SearchService(Provider(), DelayedStore()), limit)


@pytest.mark.parametrize("changed", [False, True])
async def test_sql_connection_released_during_vector_call_and_generation_revalidated(changed):
    doc, generation = uuid4(), uuid4()
    snapshots = 0
    queries = []

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        async def fetchall(self):
            return self.rows

    class Connection:
        async def execute(self, query, params=None):
            nonlocal snapshots
            queries.append((query, params))
            if query.startswith("SELECT id, vector_generation"):
                snapshots += 1
                return Cursor(
                    [
                        {
                            "id": doc,
                            "vector_generation": uuid4()
                            if changed and snapshots == 2
                            else generation,
                        }
                    ]
                )
            return Cursor([])

    class Pool:
        active = 0

        @asynccontextmanager
        async def connection(self):
            self.active += 1
            try:
                yield Connection()
            finally:
                self.active -= 1

    pool = Pool()

    class Vectors:
        async def query(self, vector, generations):
            assert pool.active == 0
            assert generations == [(doc, generation)]
            return [77]

    storage = object.__new__(Storage)
    storage.pool, storage.vectors = pool, Vectors()
    if changed:
        with pytest.raises(Conflict):
            await storage.search("policy", [doc], [1.0] * 768)
        assert not any("c.id=ANY" in query for query, _ in queries)
    else:
        assert await storage.search("policy", [doc], [1.0] * 768) == []
        hydration = [params for query, params in queries if "c.id=ANY" in query]
        assert hydration == [([doc], [77], [77])]
    assert any("FOR SHARE" in query for query, _ in queries)
    assert pool.active == 0
