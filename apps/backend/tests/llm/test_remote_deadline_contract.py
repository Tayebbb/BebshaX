import asyncio

import pytest

from bebshax.llm import AllCandidatesFailed, ChatMessage, LLMRequest, PoolRouter, TaskType
from bebshax.llm.adapters.base import AdapterCompletion, RouteCandidate, StreamDelta, StreamDone
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.latency import ATTEMPT_TIMEOUTS_S
from bebshax.llm.pools import PoolConfig
from bebshax.llm.service import SingleAdapterLLMService


def request(**changes) -> LLMRequest:
    return LLMRequest(
        task=TaskType.PERSONA_RESPONSE,
        messages=[ChatMessage(role="user", content="complete synthetic input")],
        **changes,
    )


def fake(provider="primary", adapter_type=FakeAdapter) -> FakeAdapter:
    return adapter_type([FakeRoute(candidate=RouteCandidate(provider=provider, model="model"))])


def router(primary, secondary=None, **changes) -> PoolRouter:
    return PoolRouter(
        {"freellmpool": primary, "openrouter": secondary or FakeAdapter([])},
        pools={"test": PoolConfig(name="test", adapters=["freellmpool", "openrouter"], max_concurrency=1)},
        task_pool_map={TaskType.PERSONA_RESPONSE: "test"},
        **changes,
    )


@pytest.fixture
def short_budget(monkeypatch):
    monkeypatch.setitem(ATTEMPT_TIMEOUTS_S, TaskType.PERSONA_RESPONSE, 0.02)


class SlowDiscovery(FakeAdapter):
    async def candidates(self):
        await asyncio.sleep(0.2)
        return await super().candidates()


class LateSuccess(FakeAdapter):
    async def complete(self, candidate, llm_request):
        try:
            await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            pass
        return await super().complete(candidate, llm_request)


async def test_discovery_is_inside_router_deadline(short_budget):
    records = []
    primary = fake(adapter_type=SlowDiscovery)
    service = router(primary, on_provenance=records.append)
    with pytest.raises(AllCandidatesFailed):
        await service.complete(request())
    assert len(records) == 1 and not records[0].success
    assert not records[0].attempts
    assert any("deadline" in step for step in records[0].routing_path)
    assert not service.is_cooling(RouteCandidate(provider="primary", model="model"))


async def test_admission_wait_is_inside_router_deadline(short_budget):
    records = []
    service = router(fake(), on_provenance=records.append)
    await service._semaphores["test"].acquire()
    try:
        with pytest.raises(AllCandidatesFailed):
            await asyncio.wait_for(service.complete(request()), timeout=0.15)
    finally:
        service._semaphores["test"].release()
    assert len(records) == 1 and not records[0].attempts
    assert any("deadline" in step for step in records[0].routing_path)
    assert service.pool_utilization()["test"]["active_requests"] == 0


async def test_late_success_is_not_accepted_even_if_adapter_suppresses_cancel(short_budget):
    records = []
    service = router(fake(adapter_type=LateSuccess), on_provenance=records.append)
    with pytest.raises(AllCandidatesFailed):
        await service.complete(request())
    assert not records[0].success
    assert not any(attempt.success for attempt in records[0].attempts)
    assert not service.is_cooling(RouteCandidate(provider="primary", model="model"))


async def test_single_adapter_discovery_has_the_same_deadline(short_budget):
    records = []
    service = SingleAdapterLLMService(fake(adapter_type=SlowDiscovery), on_provenance=records.append)
    with pytest.raises(AllCandidatesFailed):
        await service.complete(request())
    assert len(records) == 1 and not records[0].success


async def test_caller_cancellation_preserves_identity_without_provider_failure():
    entered = asyncio.Event()

    class Waiting(FakeAdapter):
        async def complete(self, candidate, llm_request):
            entered.set()
            await asyncio.Event().wait()

    records = []
    service = router(fake(adapter_type=Waiting), on_provenance=records.append)
    running = asyncio.create_task(service.complete(request()))
    await entered.wait()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    [attempt] = records[0].attempts
    assert attempt.failure_kind is None
    assert "abort" in (attempt.failure_detail or "")
    assert service.pool_utilization()["test"]["active_requests"] == 0


async def test_committed_stream_times_out_without_secondary_splice(short_budget):
    class StalledStream(FakeAdapter):
        async def stream(self, candidate, llm_request):
            yield StreamDelta(text="first text")
            await asyncio.sleep(0.2)
            yield StreamDone(completion=AdapterCompletion(text="first text late", provider="primary", model="model"))

    records = []
    secondary = fake("secondary")
    service = router(fake(adapter_type=StalledStream), secondary, on_provenance=records.append)
    output = []
    with pytest.raises(AttemptFailed) as failed:
        async for event in service.stream(request()):
            output.append(event)
    assert failed.value.kind == FailureKind.TIMEOUT
    assert [event.text for event in output] == ["first text"]
    assert secondary.calls == []
    assert not records[0].success


async def test_ranker_and_preferences_cannot_promote_the_secondary_tier():
    primary = fake()
    secondary = fake("secondary")
    service = router(primary, secondary, ranker=lambda entries: list(reversed(entries)))
    result = await service.complete(request(preferred_provider="secondary"))
    assert result.provider == "primary"
    assert secondary.calls == []


async def test_unhinted_recovery_probes_preserve_primary_tier_order():
    primary = fake()
    secondary = fake("secondary")
    service = router(primary, secondary, clock=lambda: 0.0)
    service._start_cooldown(RouteCandidate(provider="primary", model="model"), FailureKind.SERVER_ERROR)
    service._start_cooldown(RouteCandidate(provider="secondary", model="model"), FailureKind.TIMEOUT)
    result = await service.complete(request())
    assert result.provider == "primary"
    assert secondary.calls == []


@pytest.mark.parametrize("streaming", [False, True])
async def test_secondary_discovery_cannot_delay_an_eligible_primary(short_budget, streaming: bool) -> None:
    secondary_discovery = []

    class BlockedSecondary(FakeAdapter):
        async def candidates(self):
            secondary_discovery.append(True)
            await asyncio.Event().wait()

    service = router(fake(), fake("secondary", adapter_type=BlockedSecondary))
    if streaming:
        result = [event async for event in service.stream(request())][-1]
    else:
        result = await service.complete(request())
    assert result.provider == "primary"
    assert secondary_discovery == []


@pytest.mark.parametrize("streaming", [False, True])
async def test_secondary_catalogue_is_discovered_only_after_primary_exhaustion(streaming: bool) -> None:
    events = []

    class FailingPrimary(FakeAdapter):
        async def complete(self, candidate, llm_request):
            events.append("primary attempt")
            raise AttemptFailed(FailureKind.RATE_LIMITED, candidate.provider, candidate.model, "synthetic quota response")

    class ObservedSecondary(FakeAdapter):
        async def candidates(self):
            events.append("secondary discovery")
            return await super().candidates()

        async def complete(self, candidate, llm_request):
            events.append("secondary attempt")
            return await super().complete(candidate, llm_request)

    service = router(fake(adapter_type=FailingPrimary), fake("secondary", adapter_type=ObservedSecondary))
    if streaming:
        result = [event async for event in service.stream(request())][-1]
    else:
        result = await service.complete(request())
    assert result.provider == "secondary"
    assert events == ["primary attempt", "secondary discovery", "secondary attempt"]


@pytest.mark.parametrize("streaming", [False, True])
async def test_cancel_resistant_provider_work_keeps_its_request_admission_until_it_stops(streaming: bool) -> None:
    release = asyncio.Event()
    stopped = asyncio.Event()
    calls = []

    class CancelResistant(FakeAdapter):
        async def complete(self, candidate, llm_request):
            calls.append(llm_request.request_id)
            try:
                while not release.is_set():
                    try:
                        await release.wait()
                    except asyncio.CancelledError:
                        continue
                return AdapterCompletion(text="Late answer", provider=candidate.provider, model=candidate.model)
            finally:
                stopped.set()

    service = router(fake(adapter_type=CancelResistant))
    first = request()
    try:
        with pytest.raises(AllCandidatesFailed):
            deadline = asyncio.get_running_loop().time() + 0.025
            if streaming:
                async for _event in service.stream(first, deadline_at=deadline):
                    pytest.fail("A late stream cannot emit answer text")
            else:
                await service.complete(first, deadline_at=deadline)
        assert service.pool_utilization()["test"]["active_requests"] == 1
        assert service.pending_request_tasks()[first.request_id] >= 1
        with pytest.raises(AllCandidatesFailed):
            await service.complete(request(), deadline_at=asyncio.get_running_loop().time() + 0.02)
        assert calls == [first.request_id]
    finally:
        release.set()
        await asyncio.wait_for(stopped.wait(), timeout=1)
        if hasattr(service, "aclose"):
            await asyncio.wait_for(service.aclose(), timeout=1)
    assert service.pool_utilization()["test"]["active_requests"] == 0
    assert service.pending_request_tasks() == {}


async def test_late_provenance_callback_is_owned_by_its_request_and_drained_on_close() -> None:
    release = asyncio.Event()
    stopped = asyncio.Event()

    async def callback(record):
        try:
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    continue
        finally:
            stopped.set()

    service = SingleAdapterLLMService(fake(), on_provenance=callback)
    original = request()
    try:
        with pytest.raises(AllCandidatesFailed):
            await service.complete(original, deadline_at=asyncio.get_running_loop().time() + 0.025)
        assert service.pending_request_tasks()[original.request_id] >= 1
    finally:
        release.set()
        await asyncio.wait_for(stopped.wait(), timeout=1)
        if hasattr(service, "aclose"):
            await asyncio.wait_for(service.aclose(), timeout=1)
    assert service.pending_request_tasks() == {}