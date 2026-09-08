"""OllamaAdapter unit tests via httpx.MockTransport — no daemon, no network."""

import json

import httpx
import pytest

from bebshax.llm import AttemptFailed, ChatMessage, FailureKind, LLMRequest, TaskType
from bebshax.llm.adapters.ollama_adapter import OllamaAdapter, _required_ctx

BASE = "http://ollama.test"


def _adapter(handler, **kwargs) -> OllamaAdapter:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE)
    return OllamaAdapter(client=client, base_url=BASE, tags_ttl=0.0, **kwargs)


def _request(content="hi", **kwargs) -> LLMRequest:
    return LLMRequest(
        task=TaskType.EMERGENCY_FALLBACK,
        messages=[ChatMessage(role="user", content=content)],
        **kwargs,
    )


def _chat_ok(payload_overrides=None):
    body = {
        "model": "qwen3:4b",
        "message": {"role": "assistant", "content": "local reply"},
        "done_reason": "stop",
        "prompt_eval_count": 7,
        "eval_count": 3,
    }
    body.update(payload_overrides or {})
    return httpx.Response(200, json=body)


def _tags_and_show_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/tags":
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "qwen3.5:latest", "size": 6_600_000_000},
                    {"name": "qwen3:4b", "size": 2_600_000_000},
                ]
            },
        )
    if request.url.path == "/api/show":
        model = json.loads(request.content)["model"]
        ctx = 262_144 if model.startswith("qwen3.5") else 40_960
        return httpx.Response(200, json={"model_info": {"qwen3.context_length": ctx}})
    raise AssertionError(f"unexpected path {request.url.path}")


async def test_candidates_sorted_small_first_with_capped_windows() -> None:
    adapter = _adapter(_tags_and_show_handler, max_context_cap=16_384)
    cands = await adapter.candidates()
    assert [c.model for c in cands] == ["qwen3:4b", "qwen3.5:latest"]  # size ascending
    assert all(c.context_window == 16_384 for c in cands)  # both capped for 4 GB VRAM
    assert all(c.provider == "ollama" for c in cands)


async def test_candidates_empty_when_daemon_down() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    adapter = _adapter(handler)
    assert await adapter.candidates() == []


async def test_complete_success_maps_fields_and_sends_num_ctx() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return _chat_ok()

    adapter = _adapter(handler)
    [cand] = [c for c in await _candidates_stub()]
    completion = await adapter.complete(cand, _request(max_output_tokens=64, temperature=0.2))
    assert completion.provider == "ollama" and completion.model == "qwen3:4b"
    assert completion.usage.input_tokens == 7 and completion.usage.output_tokens == 3
    assert seen["options"]["num_ctx"] >= 4096
    assert seen["options"]["num_predict"] == 64
    assert seen["options"]["temperature"] == 0.2
    assert seen["stream"] is False


async def _candidates_stub():
    from bebshax.llm.adapters.base import RouteCandidate

    return [RouteCandidate(provider="ollama", model="qwen3:4b", context_window=16_384)]


async def test_json_mode_requests_grammar_constrained_output() -> None:
    """Found live: 2 of 3 twenty-section report replies from llama3.2:3b were
    on-topic and complete yet unparseable (a missing opening quote, a bare
    `30%`). OpenRouter already honours json_mode via response_format; the local
    adapter dropped it. Ollama's `format: "json"` constrains the sampler so
    those slips cannot be emitted."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return _chat_ok({"message": {"role": "assistant", "content": '{"questions": ["a", "b"]}'}})

    adapter = _adapter(handler)
    [cand] = await _candidates_stub()
    completion = await adapter.complete(cand, _request(json_mode=True))
    assert seen["format"] == "json"
    assert "format=json" in completion.notes

    seen.clear()
    await adapter.complete(cand, _request(json_mode=False))
    assert "format" not in seen  # free-text turns (interviews) stay unconstrained


async def test_json_mode_is_forwarded_on_the_stream_path_too() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        lines = [
            json.dumps({"message": {"role": "assistant", "content": '{"a":'}, "done": False}),
            json.dumps({"message": {"role": "assistant", "content": " 1}"}, "done": True, "done_reason": "stop", "prompt_eval_count": 3, "eval_count": 2}),
        ]
        return httpx.Response(200, text="\n".join(lines) + "\n")

    adapter = _adapter(handler)
    [cand] = await _candidates_stub()
    events = [e async for e in adapter.stream(cand, _request(json_mode=True))]
    assert seen["format"] == "json" and seen["stream"] is True
    assert events


@pytest.mark.parametrize(
    ("response", "expected_kind"),
    [
        (httpx.Response(404, text="model not found"), FailureKind.MODEL_UNAVAILABLE),
        (httpx.Response(500, text="boom"), FailureKind.SERVER_ERROR),
        (httpx.Response(429, text="busy"), FailureKind.PROVIDER_UNAVAILABLE),
        (_chat_ok({"message": {"role": "assistant", "content": "   "}}), FailureKind.MALFORMED_RESPONSE),
        (httpx.Response(200, text="not json"), FailureKind.MALFORMED_RESPONSE),
    ],
)
async def test_http_and_body_failures_map(response, expected_kind) -> None:
    adapter = _adapter(lambda request: response)
    [cand] = await _candidates_stub()
    with pytest.raises(AttemptFailed) as exc:
        await adapter.complete(cand, _request())
    assert exc.value.kind == expected_kind


async def test_transport_errors_map() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    adapter = _adapter(timeout_handler)
    [cand] = await _candidates_stub()
    with pytest.raises(AttemptFailed) as exc:
        await adapter.complete(cand, _request())
    assert exc.value.kind == FailureKind.TIMEOUT

    def connect_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    adapter = _adapter(connect_handler)
    with pytest.raises(AttemptFailed) as exc:
        await adapter.complete(cand, _request())
    assert exc.value.kind == FailureKind.CONNECTION


async def test_oversized_request_refused_not_truncated() -> None:
    adapter = _adapter(lambda request: _chat_ok())
    [cand] = await _candidates_stub()  # window 16_384
    big = _request(content="x" * 200_000)  # ≫ window with generous chars/3 estimate
    with pytest.raises(AttemptFailed) as exc:
        await adapter.complete(cand, big)
    assert exc.value.kind == FailureKind.CONTEXT_WINDOW_EXCEEDED


def test_required_ctx_is_generous_and_floored() -> None:
    small = _request(content="hi", max_output_tokens=10)
    assert _required_ctx(small) == 4096  # floor
    big = _request(content="y" * 30_000, max_output_tokens=1000)
    # ladder rung >= the shared estimator's figure (chars/3.5 + output + margin)
    assert _required_ctx(big) >= 30_000 // 3 + 1000
