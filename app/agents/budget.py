"""Request-local provider-call accounting, shared across nodes and recovery attempts."""

from contextvars import ContextVar
from dataclasses import dataclass

from .contracts import Provider


class BudgetExceeded(Exception):
    pass


@dataclass
class CallBudget:
    chat_limit: int
    embedding_limit: int
    chat_calls: int = 0
    embedding_calls: int = 0

    web_calls: int = 0

    def consume_web(self):
        if self.web_calls >= 2:
            raise BudgetExceeded("Web search limit reached")
        self.web_calls += 1

    def consume(self, kind):
        field, limit = (
            ("chat_calls", self.chat_limit)
            if kind == "chat"
            else ("embedding_calls", self.embedding_limit)
        )
        used = getattr(self, field)
        if used >= limit:
            raise BudgetExceeded("Request call budget exhausted")
        setattr(self, field, used + 1)

    def snapshot(self):
        return {
            **({"web_calls": self.web_calls, "web_limit": 2} if self.web_calls else {}),
            "chat_calls": self.chat_calls,
            "embedding_calls": self.embedding_calls,
            "chat_limit": self.chat_limit,
            "embedding_limit": self.embedding_limit,
        }


current_budget: ContextVar[CallBudget | None] = ContextVar("rag_call_budget", default=None)


@dataclass(frozen=True)
class BudgetedProvider:
    delegate: Provider

    def consume(self, kind):
        budget = current_budget.get()
        if budget is not None:
            budget.consume(kind)

    async def chat(self, *args, **kwargs):
        self.consume("chat")
        return await self.delegate.chat(*args, **kwargs)

    async def embed(self, *args, **kwargs):
        self.consume("embedding")
        return await self.delegate.embed(*args, **kwargs)

    async def stream_chat(self, *args, **kwargs):
        self.consume("chat")
        async for delta in self.delegate.stream_chat(*args, **kwargs):
            yield delta
