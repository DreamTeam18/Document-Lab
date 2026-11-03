"""Request state and structural interfaces for injected workflow dependencies."""

from collections.abc import AsyncIterator
from typing import Literal, Protocol, TypedDict


class Failure(TypedDict):
    stage: str
    code: Literal["deadline_exceeded", "provider_failure", "database_failure", "internal_failure"]
    retryable: bool


class State(TypedDict, total=False):
    status: Literal["running", "recovering", "succeeded", "failed"]
    failure: Failure | None
    deadline: float
    recovery_attempts: int
    recovery_target: str
    route: Literal["greeting", "clarify", "direct_retrieval", "complex_research"]
    resolved_question: str
    question: str
    history: str
    document_ids: list
    searches: list[str]
    hits: list[dict]
    context: str
    sources: list[dict]
    retry: bool
    answer: str
    citations: list[dict]
    warnings: list[str]


class Provider(Protocol):
    async def chat(self, system: str, prompt: str, max_tokens: int = 1200) -> str: ...

    async def embed(self, text: str) -> list[float]: ...

    def stream_chat(
        self, system: str, prompt: str, max_tokens: int = 1200
    ) -> AsyncIterator[str]: ...


class SearchStorage(Protocol):
    async def search(
        self, query: str, document_ids: list, embedding: list[float] | None
    ) -> list[dict]: ...


class Agent(Protocol):
    async def __call__(self, state: State) -> State:
        """Return a state patch without mutating the input; propagate failures/cancellation."""
        ...
