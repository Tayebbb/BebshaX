from datetime import datetime, timezone
from email.utils import format_datetime

import pytest

from bebshax.llm import AllCandidatesFailed, ChatMessage, LLMRequest, PoolRouter, TaskType
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.adapters.openrouter_adapter import _retry_after_hint
from bebshax.llm.failures import FailureKind


@pytest.mark.parametrize(
    "headers, body, expected",
    [
        ({"Retry-After": "60"}, None, 60),
        ({"retry-after": "60"}, None, 60),
        ({"Retry-After": format_datetime(datetime.fromtimestamp(1700003600, timezone.utc), usegmt=True)}, None, 3600),
        ({"X-RateLimit-Reset": "1700003600000"}, None, 3600),
        ({"x-ratelimit-reset": "1700003600"}, None, 3600),
        ({"RateLimit-Reset": "120"}, None, 120),
        ({"Retry-After": "60"}, '{"error":{"metadata":{"headers":{"X-RateLimit-Reset":"1700003600000"}}}}', 3600),
        ({"Retry-After": "NaN"}, None, None),
        ({"Retry-After": "inf"}, None, None),
        ({"Retry-After": "-1"}, None, None),
    ],
)
def test_supported_recovery_hints_take_the_longest_valid_deadline(headers, body, expected):
    assert _retry_after_hint(headers, body, now=1700000000) == expected


def make_router(**changes):
    candidate = RouteCandidate(provider="openrouter", model="model:free")
    adapter = FakeAdapter([FakeRoute(candidate=candidate)])
    return PoolRouter({"freellmpool": FakeAdapter([]), "openrouter": adapter}, **changes), adapter, candidate


def request():
    return LLMRequest(task=TaskType.PERSONA_RESPONSE, messages=[ChatMessage(role="user", content="hello")])


def test_shorter_out_of_order_hints_do_not_shorten_cooldown_or_callback():
    clock = {"now": 0.0}
    changes = []
    router, _, candidate = make_router(clock=lambda: clock["now"], on_cooldown_change=lambda *args: changes.append(args))
    router._start_cooldown(candidate, FailureKind.RATE_LIMITED, 3600)
    clock["now"] = 10.0
    router._start_cooldown(candidate, FailureKind.RATE_LIMITED, 60)
    assert router._cooldown_remaining(candidate) == 3590
    assert changes[-1] == ("openrouter", "*", 3590)


async def test_route_scoped_provider_hint_cannot_be_half_open_probed():
    router, adapter, candidate = make_router(clock=lambda: 0.0)
    router._start_cooldown(candidate, FailureKind.MODEL_UNAVAILABLE, 3600)
    with pytest.raises(AllCandidatesFailed):
        await router.complete(request())
    assert adapter.calls == []


async def test_restored_cooldown_cannot_lose_a_provider_hint():
    router, adapter, _ = make_router(clock=lambda: 0.0, initial_cooldowns={("openrouter", "model:free"): 3600})
    with pytest.raises(AllCandidatesFailed):
        await router.complete(request())
    assert adapter.calls == []


def test_long_valid_hint_is_never_capped_to_an_earlier_recovery():
    router, _, candidate = make_router(clock=lambda: 0.0)
    router._start_cooldown(candidate, FailureKind.QUOTA_EXHAUSTED, 10 * 86400)
    assert router._cooldown_remaining(candidate) == 10 * 86400