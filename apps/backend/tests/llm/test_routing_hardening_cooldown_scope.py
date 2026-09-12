"""Cooldown scope: account-level failures cool the whole provider.

Regression: a 429 on openrouter/model-a cooled only that route, so the router
walked straight into openrouter/model-b and model-c — same account, same
rate limit — burning attempts (and the interactive budget) before reaching a
route that could actually serve.
"""

import pytest

from bebshax.llm import ChatMessage, FailureKind, LLMRequest, PoolConfig, PoolRouter, TaskType
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.failures import FAILURE_POLICIES
from bebshax.llm.router import PROVIDER_WIDE, cooldown_key


def _request() -> LLMRequest:
    return LLMRequest(
        task=TaskType.PERSONA_GENERATION, messages=[ChatMessage(role="user", content="hi")]
    )


def _route(provider: str, model: str, behaviors: list | None = None) -> FakeRoute:
    return FakeRoute(
        candidate=RouteCandidate(provider=provider, model=model), behaviors=behaviors or []
    )


def _router(adapters, **kwargs):
    return PoolRouter(
        adapters,
        pools={"test": PoolConfig(name="test", adapters=["openrouter", "ollama"])},
        task_pool_map={TaskType.PERSONA_GENERATION: "test"},
        **kwargs,
    )


def test_policy_table_scopes_account_level_signals_to_the_provider() -> None:
    provider_scoped = {k for k, p in FAILURE_POLICIES.items() if p.cooldown_scope == "provider"}
    assert provider_scoped == {
        FailureKind.RATE_LIMITED,
        FailureKind.QUOTA_EXHAUSTED,
        FailureKind.AUTH_INVALID,
    }
    assert all(p.cooldown_scope in ("route", "provider") for p in FAILURE_POLICIES.values())
    # every provider-scoped policy is also a cooldown policy (scope without cooldown is meaningless)
    assert all(FAILURE_POLICIES[k].cooldown_route for k in provider_scoped)


def test_cooldown_key_shape_follows_the_policy() -> None:
    cand = RouteCandidate(provider="openrouter", model="model-a")
    assert cooldown_key(cand, FailureKind.RATE_LIMITED) == ("openrouter", PROVIDER_WIDE)
    assert cooldown_key(cand, FailureKind.SERVER_ERROR) == ("openrouter", "model-a")


async def test_rate_limited_sibling_models_are_skipped_within_the_same_request() -> None:
    persisted: list[tuple[str, str, float]] = []
    openrouter = FakeAdapter(
        [
            _route("openrouter", "model-a", [FailureKind.RATE_LIMITED]),
            _route("openrouter", "model-b"),
            _route("openrouter", "model-c"),
        ]
    )
    local = FakeAdapter([_route("ollama", "llama3.2:3b")])
    router = _router(
        {"openrouter": openrouter, "freellmpool": FakeAdapter([]), "ollama": local},
        on_cooldown_change=lambda p, m, s: persisted.append((p, m, s)),
    )

    result = await router.complete(_request())

    assert result.provider == "ollama"
    assert openrouter.calls == ["openrouter/model-a"]  # siblings never attempted
    assert local.calls == ["ollama/llama3.2:3b"]
    attempts = result.provenance.attempts
    assert [a.failure_kind for a in attempts] == [FailureKind.RATE_LIMITED, None]
    assert persisted == [("openrouter", PROVIDER_WIDE, 60.0)]
    assert router.is_cooling(RouteCandidate(provider="openrouter", model="model-b"))
    assert not router.is_cooling(RouteCandidate(provider="ollama", model="llama3.2:3b"))


async def test_provider_wide_cooldown_is_visible_in_the_next_request_and_expires() -> None:
    now = {"t": 0.0}
    openrouter = FakeAdapter(
        [
            _route("openrouter", "model-a", [FailureKind.RATE_LIMITED]),
            _route("openrouter", "model-b"),
        ]
    )
    router = _router(
        {
            "openrouter": openrouter,
            "freellmpool": FakeAdapter([]),
            "ollama": FakeAdapter([_route("ollama", "m")]),
        },
        cooldown_seconds=60.0,
        clock=lambda: now["t"],
    )
    await router.complete(_request())
    second = await router.complete(_request())
    cooling = [s for s in second.provenance.routing_path if "provider-wide" in s]
    assert len(cooling) == 2  # both openrouter routes skipped as cooling
    assert openrouter.calls == ["openrouter/model-a"]

    now["t"] = 61.0
    third = await router.complete(_request())
    assert third.provider == "openrouter"  # the provider is back after the window


async def test_route_scoped_failures_still_cool_only_their_route() -> None:
    openrouter = FakeAdapter(
        [
            _route("openrouter", "model-a", [FailureKind.SERVER_ERROR]),
            _route("openrouter", "model-b"),
        ]
    )
    router = _router(
        {"openrouter": openrouter, "freellmpool": FakeAdapter([]), "ollama": FakeAdapter([])}
    )
    result = await router.complete(_request())
    assert result.model == "model-b"  # sibling served: a 5xx on one model says nothing about the account
    assert router.is_cooling(RouteCandidate(provider="openrouter", model="model-a"))
    assert not router.is_cooling(RouteCandidate(provider="openrouter", model="model-b"))


async def test_initial_provider_wide_cooldown_from_the_store_is_honoured() -> None:
    """Restart path: a persisted (provider, "*") deadline skips every sibling."""
    openrouter = FakeAdapter([_route("openrouter", "model-a"), _route("openrouter", "model-b")])
    router = _router(
        {
            "openrouter": openrouter,
            "freellmpool": FakeAdapter([]),
            "ollama": FakeAdapter([_route("ollama", "m")]),
        },
        clock=lambda: 0.0,
        initial_cooldowns={("openrouter", PROVIDER_WIDE): 300.0},
    )
    result = await router.complete(_request())
    assert result.provider == "ollama"
    assert openrouter.calls == []


def test_frozen_policy_cannot_be_mutated_at_runtime() -> None:
    with pytest.raises(Exception):
        FAILURE_POLICIES[FailureKind.RATE_LIMITED].cooldown_scope = "route"  # type: ignore[misc]
