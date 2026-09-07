"""freellmpool attempt budget: the per-task timeout bounds the WHOLE attempt.

Regression: freellmpool applies `timeout` per inner target, so its internal
failover across N targets could stretch a single BebshaX attempt to N×budget
— an interactive turn budgeted at 25s could block for minutes before the
router was allowed to advance to the local tier.
"""

import asyncio
import time

import pytest

from bebshax.llm import AttemptFailed, ChatMessage, FailureKind, LLMRequest, TaskType
from bebshax.llm.adapters import freellmpool_adapter
from bebshax.llm.adapters.freellmpool_adapter import FreellmpoolAdapter


class SlowPool:
    """Stands in for AsyncPool: honours nothing, just sleeps past the budget."""

    def __init__(self, sleep_s: float) -> None:
        self._sleep_s = sleep_s
        self.calls = 0
        self.cancelled = False

    async def achat(self, messages, **kwargs):
        self.calls += 1
        try:
            await asyncio.sleep(self._sleep_s)
        except asyncio.CancelledError:
            self.cancelled = True  # wait_for cancels the in-flight inner call
            raise
        raise AssertionError("achat should have been cancelled by the attempt budget")

    async def aclose(self) -> None:
        pass


def _request() -> LLMRequest:
    return LLMRequest(
        task=TaskType.PERSONA_RESPONSE,
        messages=[ChatMessage(role="user", content="hi")],
    )


async def test_attempt_exceeding_budget_is_a_timeout_raised_within_budget(monkeypatch) -> None:
    budget = 0.05
    monkeypatch.setattr(freellmpool_adapter, "attempt_timeout_s", lambda task: budget)
    pool = SlowPool(sleep_s=5.0)
    adapter = FreellmpoolAdapter(pool=pool)
    [candidate] = await adapter.candidates()

    t0 = time.perf_counter()
    with pytest.raises(AttemptFailed) as exc:
        await adapter.complete(candidate, _request())
    elapsed = time.perf_counter() - t0

    assert exc.value.kind == FailureKind.TIMEOUT
    assert exc.value.detail == "attempt budget exceeded"
    assert isinstance(exc.value.__cause__, asyncio.TimeoutError)
    assert elapsed < 2.0  # budget-bound, not sleep-bound
    assert pool.calls == 1 and pool.cancelled  # inner call was actually cut off


async def test_inner_timeout_and_outer_budget_are_the_same_number(monkeypatch) -> None:
    """The per-target timeout handed to freellmpool equals the attempt budget,
    so a single healthy target still gets the full budget."""
    monkeypatch.setattr(freellmpool_adapter, "attempt_timeout_s", lambda task: 12.5)

    class RecordingPool:
        def __init__(self) -> None:
            self.kwargs: dict = {}

        async def achat(self, messages, **kwargs):
            self.kwargs = kwargs
            from freellmpool import Reply

            return Reply(
                text="ok", provider_id="llm7", model="m", raw={},
                prompt_tokens=1, completion_tokens=1, attempts=1, cached=False,
            )

        async def aclose(self) -> None:
            pass

    pool = RecordingPool()
    adapter = FreellmpoolAdapter(pool=pool)
    [candidate] = await adapter.candidates()
    completion = await adapter.complete(candidate, _request())
    assert completion.text == "ok"
    assert pool.kwargs["timeout"] == 12.5
