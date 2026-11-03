"""Callable nodes with injected dependencies and request-local execution state.

No base-class exception conversion: provider failures and cancellation propagate
unchanged to the caller. Expected embedding failures retain the existing fallback.
"""

import asyncio
import time
from dataclasses import dataclass

from app.providers import ProviderError

from .assessment import AssessmentAgent as AssessmentAgent
from .budget import current_budget
from .contracts import Provider, SearchStorage, State
from .evidence import prepare_evidence
from .planning import PlanningAgent as PlanningAgent
from .planning import single_question_plan
from .synthesis import AnsweringAgent as AnsweringAgent


@dataclass(frozen=True)
class SearchService:
    providers: Provider
    storage: SearchStorage

    async def search(self, queries: list[str], document_ids: list) -> tuple[list[dict], list[str]]:
        hits, warnings = {}, []
        for query in queries:
            try:
                embedding = await self.providers.embed(query)
            except ProviderError:
                embedding = None
                warnings.append("Embedding service unavailable; used exact/full-text retrieval.")
            for hit in await self.storage.search(query, document_ids, embedding):
                hits.setdefault(hit["id"], hit)
        return list(hits.values())[:12], warnings


@dataclass(frozen=True)
class RetrievalAgent:
    search: SearchService
    concurrency: int = 2
    service_limiter: asyncio.Semaphore | None = None

    def __post_init__(self):
        if not 1 <= self.concurrency <= 4:
            raise ValueError("Research concurrency must be between one and four")

    async def __call__(self, state: State) -> State:
        plan = state.get("research_plan") or single_question_plan(
            state["searches"][0], state["document_ids"]
        )
        collected, warnings, results = {}, list(state.get("warnings", [])), []
        local_limiter = asyncio.Semaphore(self.concurrency)
        service_limiter = self.service_limiter or local_limiter
        budget = current_budget.get()
        # Allocate optional embeddings deterministically before workers run. Reserve
        # all original searches plus one refinement, independent of completion order.
        slots = (
            max(0, budget.embedding_limit - budget.embedding_calls - len(plan) - 1)
            if budget
            else len(plan)
        )
        optional = {item["id"] for item in plan if state.get("hyde_passages", {}).get(item["id"])}
        optional = set([item["id"] for item in plan if item["id"] in optional][:slots])
        failures = {}

        async def search_item(item):
            started = time.monotonic()
            try:
                async with local_limiter:
                    # No double acquisition when running outside the API service.
                    if self.service_limiter is not None:
                        async with service_limiter:
                            hits, notices = await execute(item)
                    else:
                        hits, notices = await execute(item)
                return {
                    "sub_question_id": item["id"],
                    "hits": hits,
                    "status": "retrieved" if hits else "empty",
                    "warnings": notices,
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                }
            except ProviderError as exc:
                failures[item["id"]] = exc
                return {
                    "sub_question_id": item["id"],
                    "hits": [],
                    "status": "failed",
                    "warnings": ["Research failed for " + item["id"] + "; evidence is incomplete."],
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                }

        async def execute(item):
            hits, notices = await self.search.search([item["question"]], state["document_ids"])
            passage = state.get("hyde_passages", {}).get(item["id"])
            if passage and item["id"] in optional:
                try:
                    vector = await self.search.providers.embed(passage)
                    extra = await self.search.storage.search(
                        item["question"], state["document_ids"], vector
                    )
                    merged = {}
                    for rank in range(max(len(hits), len(extra))):
                        for batch in (hits, extra):
                            if rank < len(batch):
                                merged.setdefault(batch[rank]["id"], batch[rank])
                    hits = list(merged.values())[:12]
                except ProviderError:
                    notices.append("HyDE search unavailable; retained original-query evidence.")
            elif passage:
                notices.append("HyDE embedding skipped to preserve the retrieval call budget.")
            return hits, notices

        completed = {}
        pending = list(plan)
        while pending:
            ready = [
                item for item in pending if all(dep in completed for dep in item["dependencies"])
            ]
            if not ready:
                raise ValueError("Invalid research dependencies")
            runnable = []
            for item in ready:
                if any(
                    completed[dep]["status"] in {"failed", "blocked"}
                    for dep in item["dependencies"]
                ):
                    completed[item["id"]] = {
                        "sub_question_id": item["id"],
                        "hits": [],
                        "status": "blocked",
                        "warnings": [
                            "Research blocked by a failed dependency for " + item["id"] + "."
                        ],
                        "elapsed_ms": 0,
                    }
                else:
                    runnable.append(item)
            tasks = [asyncio.create_task(search_item(item)) for item in runnable]
            try:
                batch = await asyncio.gather(*tasks)
            except BaseException:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            completed.update({result["sub_question_id"]: result for result in batch})
            pending = [item for item in pending if item not in ready]
        results = [completed[item["id"]] for item in plan]
        if failures and not any(result["status"] in {"retrieved", "empty"} for result in results):
            # Uniform failure retains the graph's bounded retry/error semantics.
            raise failures[next(item["id"] for item in plan if item["id"] in failures)]
        for result in results:
            warnings.extend(result["warnings"])
            for hit in result["hits"]:
                collected.setdefault(hit["id"], hit)
        hits = list(collected.values())[:12]
        context, sources = prepare_evidence(hits)
        return {
            "hits": hits,
            "context": context,
            "sources": sources,
            "warnings": warnings,
            "research_plan": plan,
            "plan_size": len(plan),
            "research_results": results,
            "hyde_passages": {},
        }


@dataclass(frozen=True)
class RefinementAgent:
    search: SearchService

    async def __call__(self, state: State) -> State:
        hits, warnings = await self.search.search(state["searches"], state["document_ids"])
        results = []
        for result in state.get("research_results", []):
            if result["sub_question_id"] == state.get("refinement_target"):
                unique = {h["id"]: h for h in hits + result["hits"]}
                results.append(
                    {
                        **result,
                        "hits": list(unique.values())[:12],
                        "status": "retrieved" if unique else "empty",
                    }
                )
            else:
                results.append(result)
        unique = {h["id"]: h for h in hits + state["hits"]}
        context, sources = prepare_evidence(list(unique.values())[:12])
        return {
            "context": context,
            "sources": sources,
            "hits": list(unique.values())[:12],
            "research_results": results,
            "refinement_attempts": state.get("refinement_attempts", 0) + 1,
            "warnings": state["warnings"] + warnings,
        }
