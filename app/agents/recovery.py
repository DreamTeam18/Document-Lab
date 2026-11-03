"""Explicit recovery edges with a request-wide deadline and retry budget."""

import asyncio
import logging
import time
from dataclasses import dataclass

from psycopg import Error as DatabaseError

from app.providers import ProviderError

from .contracts import Agent, Failure, State

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GuardedAgent:
    stage: str
    agent: Agent
    timeout_seconds: float

    async def __call__(self, state: State) -> State:
        started = time.monotonic()
        deadline = state.get("deadline", started + self.timeout_seconds)
        try:
            # A standalone graph invocation receives the same bound as the API.
            async with asyncio.timeout_at(deadline):
                patch = await self.agent(state)
            return {
                **patch,
                "deadline": deadline,
                "failure": None,
                "status": "succeeded" if self.stage in {"answer", "conversational"} else "running",
            }
        except TimeoutError:
            code, retryable = "deadline_exceeded", False
        except ProviderError as exc:
            code, retryable = "provider_failure", exc.retryable
        except DatabaseError:
            code, retryable = "database_failure", False
        except Exception:
            # Never put exception messages/bodies, prompts or DSNs into graph state.
            code, retryable = "internal_failure", False
        # CancelledError is a BaseException and deliberately bypasses this handler.
        failure: Failure = {"stage": self.stage, "code": code, "retryable": retryable}
        logger.warning(
            "Workflow stage failed stage=%s code=%s elapsed_ms=%d",
            self.stage,
            code,
            int((time.monotonic() - started) * 1000),
        )
        return {"deadline": deadline, "failure": failure, "status": "recovering"}


@dataclass(frozen=True)
class ErrorHandlerAgent:
    # Total additional attempts across the request, not per-node allowances.
    max_retries: int = 2
    retry_delay: float = 0.25

    async def __call__(self, state: State) -> State:
        failure = state["failure"]
        assert failure is not None
        used = state.get("recovery_attempts", 0)
        delay = self.retry_delay * (2**used)
        # Never replay synthesis: it may already have emitted user-visible tokens.
        can_retry = (
            failure["retryable"]
            and failure["stage"] in {"triage", "plan", "retrieve", "assess", "refine"}
            and used < self.max_retries
            and time.monotonic() + delay < state["deadline"]
        )
        if can_retry:
            try:
                async with asyncio.timeout_at(state["deadline"]):
                    await asyncio.sleep(delay)
            except TimeoutError:
                return {
                    "status": "failed",
                    "recovery_target": "end",
                    "answer": "",
                    "citations": [],
                    "failure": {**failure, "code": "deadline_exceeded", "retryable": False},
                }
            return {
                "status": "running",
                "recovery_attempts": used + 1,
                "recovery_target": failure["stage"],
                "failure": None,
            }
        return {
            "status": "failed",
            "recovery_target": "end",
            "answer": "",
            "citations": [],
        }
