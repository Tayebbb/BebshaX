"""Streaming contract: adapter default fallback, Ollama NDJSON, and router
commit-on-first-delta semantics."""

import json

import httpx
import pytest

from bebshax.llm import LLMResult
from bebshax.llm.adapters.base import RouteCandidate, StreamDelta, StreamDone
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.adapters.ollama_adapter import OllamaAdapter
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.router import PoolRouter
from bebshax.llm.pools import PoolConfig
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType


def _request(**kw) -> LLMRequest:
    return LLMRequest(
        task=kw.pop("task", TaskType.PERSONA_INTERVIEW),
        messages=[ChatMessage(role="user", content="hi")],
        **kw,
    )


async def _collect(agen):
    events = []
    async for e in agen:
        events.append(e)
    return events


# ---------------------------------------------------------------------------
# Base adapter default: one delta carrying the full completion
# ---------------------------------------------------------------------------

async def test_default_stream_yields_full_text_once() -> None:
    adapter = FakeAdapter(
        [FakeRoute(candidate=RouteCandidate(provider="fake", model="m"), reply="hello world")]
    )
    [cand] = await adapter.candidates()
    events = await _collect(adapter.stream(cand, _request()))
    assert [type(e) for e in events] == [StreamDelta, StreamDone]
    assert events[0].text == "hello world"
    assert events[1].completion.text == "hello world"


# ---------------------------------------------------------------------------
# Ollama native NDJSON streaming
# ---------------------------------------------------------------------------

def _ndjson_transport(lines: list[dict], status: int = 200) -> httpx.MockTransport:
    body = "\n".join(json.dumps(line) for line in lines)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body.encode())

    return httpx.MockTransport(handler)


def _ollama(transport: httpx.MockTransport) -> OllamaAdapter:
    client = httpx.AsyncClient(base_url="http://test", transport=transport)
    return OllamaAdapter(client=client)


_CAND = RouteCandidate(provider="ollama", model="llama3.2:3b", context_window=8192)


async def test_ollama_stream_accumulates_deltas_and_usage() -> None:
    adapter = _ollama(
        _ndjson_transport(
            [
                {"message": {"content": "Hel"}, "done": False},
                {"message": {"content": "lo"}, "done": False},
                {
                    "message": {"content": ""},
                    "done": True,
                    "model": "llama3.2:3b",
                    "prompt_eval_count": 12,
                    "eval_count": 2,
                },
            ]
        )
    )
    events = await _collect(adapter.stream(_CAND, _request()))
    deltas = [e.text for e in events if isinstance(e, StreamDelta)]
    done = events[-1]
    assert deltas == ["Hel", "lo"]
    assert isinstance(done, StreamDone)
    assert done.completion.text == "Hello"
    assert done.completion.usage.output_tokens == 2
    assert "streamed" in done.completion.notes


async def test_ollama_stream_empty_is_malformed() -> None:
    adapter = _ollama(_ndjson_transport([{"message": {"content": ""}, "done": True}]))
    with pytest.raises(AttemptFailed) as exc:
        await _collect(adapter.stream(_CAND, _request()))
    assert exc.value.kind == FailureKind.MALFORMED_RESPONSE


# ---------------------------------------------------------------------------
# Router stream: pre-first-delta failures advance; provenance is complete
# ---------------------------------------------------------------------------

def _router(adapters: dict, on_provenance=None) -> PoolRouter:
    return PoolRouter(
        adapters,
        pools={
            "conversation": PoolConfig(
                name="conversation", adapters=list(adapters.keys()), max_concurrency=2
            )
        },
        task_pool_map={TaskType.PERSONA_INTERVIEW: "conversation"},
        on_provenance=on_provenance,
    )


async def test_router_stream_yields_deltas_then_result_with_provenance() -> None:
    records = []
    fake = FakeAdapter(
        [FakeRoute(candidate=RouteCandidate(provider="fake", model="m1"), reply="streamed answer")]
    )
    router = _router({"fake": fake}, on_provenance=records.append)
    events = await _collect(router.stream(_request()))
    assert isinstance(events[0], StreamDelta) and events[0].text == "streamed answer"
    final = events[-1]
    assert isinstance(final, LLMResult)
    assert final.provider == "fake" and final.text == "streamed answer"
    assert records and records[0].success is True
    assert records[0].served_by_model == "m1"


async def test_router_stream_advances_past_prefirst_delta_failure() -> None:
    failing = FakeAdapter(
        [
            FakeRoute(
                candidate=RouteCandidate(provider="fake", model="dead"),
                behaviors=[FailureKind.SERVER_ERROR, FailureKind.SERVER_ERROR],
            )
        ]
    )
    healthy = FakeAdapter(
        [FakeRoute(candidate=RouteCandidate(provider="fake2", model="ok"), reply="recovered")]
    )
    router = _router({"a": failing, "b": healthy})
    events = await _collect(router.stream(_request()))
    final = events[-1]
    assert isinstance(final, LLMResult)
    assert final.model == "ok"
    kinds = [a.failure_kind for a in final.provenance.attempts if a.failure_kind]
    assert FailureKind.SERVER_ERROR in kinds  # the dead route was really tried


class MidStreamFailingAdapter(FakeAdapter):
    """Emits deltas, then dies — for the commit-on-first-delta semantic."""

    def __init__(self, routes, deltas_before_death: list[str]):
        super().__init__(routes)
        self._deltas = deltas_before_death

    async def stream(self, candidate, request):
        for d in self._deltas:
            yield StreamDelta(text=d)
        raise AttemptFailed(
            FailureKind.SERVER_ERROR, candidate.provider, candidate.model, "died mid-answer"
        )


async def test_router_stream_never_swaps_route_after_first_delta() -> None:
    """Once a route has spoken, its failure SURFACES — no mid-answer splice (R2)."""
    records = []
    dying = MidStreamFailingAdapter(
        [FakeRoute(candidate=RouteCandidate(provider="fake", model="talker"))],
        deltas_before_death=["Hel", "lo"],
    )
    healthy = FakeAdapter(
        [FakeRoute(candidate=RouteCandidate(provider="fake2", model="ok"), reply="never used")]
    )
    router = _router({"a": dying, "b": healthy}, on_provenance=records.append)

    received: list[str] = []
    with pytest.raises(AttemptFailed) as exc:
        async for e in router.stream(_request()):
            if isinstance(e, StreamDelta):
                received.append(e.text)
    assert received == ["Hel", "lo"]
    assert exc.value.kind == FailureKind.SERVER_ERROR
    # provenance fired despite the failure, healthy route untouched
    assert records and records[0].success is False
    tried = {(a.provider, a.model) for a in records[0].attempts}
    assert tried == {("fake", "talker")}


async def test_router_stream_retries_same_route_once_per_policy() -> None:
    """MALFORMED_RESPONSE has retry_same_once=True — the stream path must
    honor the same FAILURE_POLICIES table as complete()."""
    flaky = FakeAdapter(
        [
            FakeRoute(
                candidate=RouteCandidate(provider="fake", model="flaky"),
                behaviors=[FailureKind.MALFORMED_RESPONSE],  # first call fails, second succeeds
                reply="second try worked",
            )
        ]
    )
    router = _router({"a": flaky})
    events = await _collect(router.stream(_request()))
    final = events[-1]
    assert isinstance(final, LLMResult)
    assert final.text == "second try worked"
    assert len(final.provenance.attempts) == 2
    assert final.provenance.attempts[0].fallback_reason == "retrying same route once"


async def test_router_stream_frees_pool_slot_when_consumer_breaks_early() -> None:
    """Breaking out of the stream (with aclosing) must release the semaphore
    and fire provenance immediately — not at GC (critic finding #1)."""
    from contextlib import aclosing

    records = []
    fake = FakeAdapter(
        [FakeRoute(candidate=RouteCandidate(provider="fake", model="m1"), reply="answer")]
    )
    router = _router({"fake": fake}, on_provenance=records.append)

    async with aclosing(router.stream(_request())) as stream:
        async for event in stream:
            if isinstance(event, LLMResult):
                break
    assert router.pool_utilization()["conversation"]["active_requests"] == 0
    assert records and records[0].success is True
    # The close-after-done GeneratorExit must never mislabel a successful
    # attempt as aborted (round-2 critic finding).
    assert records[0].attempts[-1].failure_detail is None


async def test_router_stream_stamps_abort_when_consumer_breaks_before_done() -> None:
    """Breaking BEFORE StreamDone is a real abort: the attempt must be
    stamped 'aborted by consumer' so provenance never hides a partial
    stream as a full success (round-3 critic finding)."""
    from contextlib import aclosing

    records = []
    fake = FakeAdapter(
        [FakeRoute(candidate=RouteCandidate(provider="fake", model="m1"), reply="answer")]
    )
    router = _router({"fake": fake}, on_provenance=records.append)

    async with aclosing(router.stream(_request())) as stream:
        async for event in stream:
            if isinstance(event, StreamDelta):
                break  # abandon mid-stream, before the final LLMResult
    assert router.pool_utilization()["conversation"]["active_requests"] == 0
    assert records and records[0].success is False
    assert records[0].attempts[-1].failure_detail == "aborted by consumer"
    assert records[0].attempts[-1].success is False
