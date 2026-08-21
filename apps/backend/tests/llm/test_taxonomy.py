from bebshax.llm import FAILURE_POLICIES, FailureKind


def test_every_failure_kind_has_a_policy() -> None:
    assert set(FAILURE_POLICIES) == set(FailureKind)


def test_low_quality_is_not_an_infrastructure_failure() -> None:
    # Owner rule (2026-08-22): quality belongs to the evaluation layer,
    # never to infrastructure fallback.
    assert not any("QUALITY" in kind.name for kind in FailureKind)


def test_internal_error_never_advances_the_chain() -> None:
    policy = FAILURE_POLICIES[FailureKind.INTERNAL_ERROR]
    assert policy.try_next_candidate is False
    assert policy.retry_same_once is False


def test_context_overflow_advances_without_cooldown() -> None:
    policy = FAILURE_POLICIES[FailureKind.CONTEXT_WINDOW_EXCEEDED]
    assert policy.try_next_candidate is True
    assert policy.cooldown_route is False
