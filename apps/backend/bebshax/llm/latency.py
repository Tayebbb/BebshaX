"""Per-attempt latency budgets by task class — data table, not code branches.

An attempt may use only the time remaining on the absolute request deadline.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import TypeVar

from bebshax.llm.types import TaskType

_active_deadline: ContextVar[float | None] = ContextVar("llm_deadline", default=None)
_Result = TypeVar("_Result")
_pending_cleanup: set[asyncio.Future] = set()


class RequestTaskOwner:
    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        self.finished = asyncio.Event()
        self._tasks: set[asyncio.Future] = set()
        self._cleanup: list[Callable[[], Awaitable]] = []

    @property
    def pending_count(self) -> int:
        return len(self._tasks) + len(self._cleanup)

    def retain(self, task: asyncio.Future) -> None:
        if task not in self._tasks:
            self._tasks.add(task)
            task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Future) -> None:
        self._tasks.discard(task)
        if not task.cancelled():
            task.exception()

    def defer_cleanup(self, callback: Callable[[], Awaitable]) -> None:
        self._cleanup.append(callback)

    async def drain(self) -> None:
        while self._tasks or self._cleanup:
            while self._tasks:
                await asyncio.gather(*tuple(self._tasks), return_exceptions=True)
            callbacks, self._cleanup = self._cleanup, []
            for callback in callbacks:
                await callback()


_active_task_owner: ContextVar[RequestTaskOwner | None] = ContextVar("llm_task_owner", default=None)


class DeadlineExpired(TimeoutError):
    """The application's absolute budget expired, not a provider health signal."""

DEFAULT_ATTEMPT_TIMEOUT_S = 90.0

# Interactive surfaces (a human is watching a spinner).
_INTERACTIVE_S = 25.0
# Structured/generation calls (progress UI, retry affordable).
_STANDARD_S = 75.0
# Long-context synthesis (large outputs are legitimately slow).
_LONG_S = 150.0

ATTEMPT_TIMEOUTS_S: dict[TaskType, float] = {
    TaskType.PERSONA_INTERVIEW: _INTERACTIVE_S,
    TaskType.PERSONA_RESPONSE: _INTERACTIVE_S,
    TaskType.MEMORY_RETRIEVAL: _INTERACTIVE_S,
    TaskType.MEMORY_SUMMARIZATION: _INTERACTIVE_S,
    TaskType.EMERGENCY_FALLBACK: _INTERACTIVE_S,
    TaskType.PERSONA_GENERATION: _STANDARD_S,
    TaskType.PERSONA_REFINEMENT: _STANDARD_S,
    TaskType.PERSONA_VALIDATION: _STANDARD_S,
    TaskType.PERSONA_NARRATIVE: _STANDARD_S,
    TaskType.BEHAVIORAL_SIMULATION: _STANDARD_S,
    TaskType.EVIDENCE_EXTRACTION: _STANDARD_S,
    TaskType.EVIDENCE_CLASSIFICATION: _STANDARD_S,
    TaskType.CONTRADICTION_CHECK: _STANDARD_S,
    TaskType.CRITIC: _STANDARD_S,
    TaskType.STRUCTURED_OUTPUT: _STANDARD_S,
    TaskType.BROWSER_AGENT: _STANDARD_S,
    TaskType.TOOL_CALLING: _STANDARD_S,
    TaskType.REPORT_GENERATION: _LONG_S,
}


def attempt_timeout_s(task: TaskType) -> float:
    return ATTEMPT_TIMEOUTS_S.get(task, DEFAULT_ATTEMPT_TIMEOUT_S)


# Whole-request wall-clock budget: the fallback chain may not keep a caller
# waiting through every slow route. After each failed attempt the loop stops
# once this much time has elapsed and reports exhaustion with the trail so far.
REQUEST_DEADLINE_MULTIPLIER = 2.5
REQUEST_DEADLINE_CAP_S = 300.0


def request_deadline_s(task: TaskType) -> float:
    return min(REQUEST_DEADLINE_CAP_S, attempt_timeout_s(task) * REQUEST_DEADLINE_MULTIPLIER)


def resolve_deadline(
    task: TaskType, *, deadline_at: float | None = None, budget_s: float | None = None
) -> float:
    local = asyncio.get_running_loop().time() + (
        request_deadline_s(task) if budget_s is None else budget_s
    )
    return min(value for value in (local, deadline_at, _active_deadline.get()) if value is not None)


def remaining_attempt_timeout_s(task: TaskType) -> float:
    budget = attempt_timeout_s(task)
    deadline = _active_deadline.get()
    if deadline is not None:
        budget = min(budget, deadline - asyncio.get_running_loop().time())
    if budget <= 0:
        raise DeadlineExpired("absolute request deadline exceeded")
    return budget


async def await_before(
    operation: Awaitable[_Result], deadline_at: float, *, task_owner: RequestTaskOwner | None = None,
) -> _Result:
    loop = asyncio.get_running_loop()
    inherited = _active_deadline.get()
    deadline = min(deadline_at, inherited) if inherited is not None else deadline_at
    if loop.time() >= deadline:
        if inspect.iscoroutine(operation):
            operation.close()
        raise DeadlineExpired("absolute request deadline exceeded")
    token = _active_deadline.set(deadline)
    owner = task_owner if task_owner is not None else _active_task_owner.get()
    owner_token = _active_task_owner.set(owner)
    try:
        pending = asyncio.ensure_future(operation)
    finally:
        _active_task_owner.reset(owner_token)
        _active_deadline.reset(token)
    try:
        finished, _ = await asyncio.wait({pending}, timeout=max(0.0, deadline - loop.time()))
    except asyncio.CancelledError as exc:
        setattr(exc, "observations", await _cancel_operation(pending, owner))
        raise
    if not finished or loop.time() >= deadline:
        observations = await _cancel_operation(pending, owner)
        expired = DeadlineExpired("late result rejected after absolute request deadline")
        setattr(expired, "observations", observations)
        raise expired
    return pending.result()


def _consume_cleanup(task: asyncio.Future) -> None:
    _pending_cleanup.discard(task)
    if not task.cancelled():
        task.exception()


async def _cancel_operation(task: asyncio.Future, owner: RequestTaskOwner | None = None) -> list:
    for _ in range(2):
        if task.done():
            break
        task.cancel()
        await asyncio.wait({task}, timeout=0.01)
    if not task.done():
        if owner is not None:
            owner.retain(task)
        else:
            _pending_cleanup.add(task)
            task.add_done_callback(_consume_cleanup)
        return []
    try:
        error = task.exception()
        if error is not None:
            return list(getattr(error, "observations", getattr(getattr(error, "failure", None), "observations", [])))
        return list(getattr(task.result(), "observations", []))
    except asyncio.CancelledError as exc:
        return list(getattr(exc, "observations", []))


class DeadlineContext:
    """Bound context entry/cleanup without leaving a task timeout across yields."""

    def __init__(self, manager, deadline: float, *, task_owner: RequestTaskOwner | None = None):
        self._manager = manager
        self._deadline = deadline
        self._closed = False
        self._task_owner = task_owner if task_owner is not None else _active_task_owner.get()

    async def __aenter__(self):
        return await await_before(self._manager.__aenter__(), self._deadline, task_owner=self._task_owner)

    async def aclose(self, exc_type=None, exc=None, traceback=None):
        if self._closed:
            return False
        self._closed = True
        token = _active_deadline.set(None)
        try:
            deadline = self._deadline if exc is None else min(self._deadline, asyncio.get_running_loop().time() + 0.01)
            deadline = max(deadline, asyncio.get_running_loop().time() + 0.001)
            try:
                return await await_before(self._manager.__aexit__(exc_type, exc, traceback), deadline, task_owner=self._task_owner)
            except Exception as cleanup_error:
                if isinstance(cleanup_error, RuntimeError) and "already running" in str(cleanup_error) and self._task_owner is not None:
                    self._task_owner.defer_cleanup(lambda: self._manager.__aexit__(exc_type, exc, traceback))
                if exc is None:
                    raise
                return False
        finally:
            _active_deadline.reset(token)

    async def __aexit__(self, exc_type, exc, traceback):
        return await self.aclose(exc_type, exc, traceback)
