"""Latency budgets: task-class attempt timeouts and their adapter wiring."""

from bebshax.llm.adapters.factory import build_default_adapters
from bebshax.llm.latency import (
    ATTEMPT_TIMEOUTS_S,
    DEFAULT_ATTEMPT_TIMEOUT_S,
    attempt_timeout_s,
)
from bebshax.llm.types import TaskType


def test_every_task_type_has_a_budget() -> None:
    missing = [t for t in TaskType if t not in ATTEMPT_TIMEOUTS_S]
    assert not missing, f"tasks without a latency budget: {missing}"


def test_interactive_tasks_are_tight() -> None:
    assert attempt_timeout_s(TaskType.PERSONA_INTERVIEW) <= 30
    assert attempt_timeout_s(TaskType.PERSONA_RESPONSE) <= 30
    assert attempt_timeout_s(TaskType.EMERGENCY_FALLBACK) <= 30


def test_long_context_gets_headroom() -> None:
    assert attempt_timeout_s(TaskType.REPORT_GENERATION) > attempt_timeout_s(
        TaskType.PERSONA_INTERVIEW
    )


def test_unknown_falls_back_to_default() -> None:
    class _Fake:  # not a TaskType member
        pass

    assert attempt_timeout_s(_Fake()) == DEFAULT_ATTEMPT_TIMEOUT_S  # type: ignore[arg-type]


def test_factory_uses_fast_routing_for_freellmpool() -> None:
    adapters = build_default_adapters()
    assert adapters["freellmpool"]._routing == "fast"
