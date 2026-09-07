"""Script-aware shared token estimator and its use for Ollama num_ctx sizing.

Regression: the old chars/3.5 heuristic rated an 8,000-character Bangla prompt
at ~2,300 tokens; byte-level BPE vocabularies spend >= 1 token per Bangla
character, so Ollama received a num_ctx far below the real prompt size and
silently truncated (R2). Estimation is now ONE function used by the router's
eligibility check and by the adapter's num_ctx choice.
"""

import json

import httpx

from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.ollama_adapter import OllamaAdapter, _choose_num_ctx, _required_ctx
from bebshax.llm.estimator import (
    DEFAULT_EXPECTED_OUTPUT_TOKENS,
    estimate_request_tokens,
    estimate_text_tokens,
)
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType

_BANGLA_SENTENCE = "আমি ঢাকায় থাকি এবং প্রতিদিন সকালে পড়াশোনা করি। "


def _bangla(chars: int) -> str:
    text = _BANGLA_SENTENCE * (chars // len(_BANGLA_SENTENCE) + 1)
    return text[:chars]


def _request(content: str, **kwargs) -> LLMRequest:
    return LLMRequest(
        task=TaskType.PERSONA_INTERVIEW,
        messages=[ChatMessage(role="user", content=content)],
        **kwargs,
    )


def test_bangla_prompt_counts_at_least_one_token_per_character() -> None:
    text = _bangla(8_000)
    assert len(text) == 8_000
    # ≥1 token per non-ASCII char: the estimate must be in the thousands, not ~2,300
    assert estimate_text_tokens(text) >= 6_000
    assert estimate_request_tokens(_request(text)) >= 6_000


def test_english_estimate_stays_within_fifteen_percent_of_old_value() -> None:
    text = ("The quick brown fox jumps over the lazy dog. " * 100)[:3_500]
    assert text.isascii() and len(text) == 3_500
    old_value = int(3_500 / 3.5) + 4 + DEFAULT_EXPECTED_OUTPUT_TOKENS  # pre-fix formula
    new_value = estimate_request_tokens(_request(text))
    assert old_value <= new_value <= old_value * 1.15  # only the safety margin moved it


def test_estimate_includes_max_output_and_safety_margin() -> None:
    base = estimate_request_tokens(_request("x" * 350, max_output_tokens=100))
    # ascii 350/3.5 = 100 tokens + 4 framing + 100 output = 204 → ×1.1 = 225 (ceil)
    assert base == 225
    # explicit output budget replaces the default allowance
    assert estimate_request_tokens(_request("x" * 350, max_output_tokens=1000)) > base
    assert estimate_text_tokens("") == 0


def test_choose_num_ctx_is_a_ladder_rung_never_below_estimate_capped_at_window() -> None:
    assert _choose_num_ctx(100, 16_384) == 4_096  # floor
    assert _choose_num_ctx(5_000, 16_384) == 8_192  # smallest rung >= estimate
    assert _choose_num_ctx(8_192, 16_384) == 8_192  # exact rung fits
    assert _choose_num_ctx(8_193, 16_384) == 16_384
    assert _choose_num_ctx(17_000, 20_000) == 20_000  # no rung fits below the window → window
    assert _required_ctx(_request(_bangla(5_000))) >= estimate_request_tokens(_request(_bangla(5_000)))


async def test_ollama_sends_num_ctx_at_least_the_shared_estimate_for_bangla() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "qwen3:4b",
                "message": {"role": "assistant", "content": "ঠিক আছে"},
                "done_reason": "stop",
                "prompt_eval_count": 6000,
                "eval_count": 3,
            },
        )

    adapter = OllamaAdapter(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://t"),
        base_url="http://t",
    )
    cand = RouteCandidate(provider="ollama", model="qwen3:4b", context_window=16_384)
    text = _bangla(5_000)
    request = _request(text, max_output_tokens=512)
    estimate = estimate_request_tokens(request)

    # The retired private heuristic (chars//3 + output + 256, rounded to 1k,
    # floor 4k) would have asked for 4096 — below what the prompt needs.
    old_num_ctx = max((((len(text) // 3) + 512 + 256 + 1023) // 1024) * 1024, 4096)
    assert estimate > old_num_ctx

    completion = await adapter.complete(cand, request)
    assert seen["options"]["num_ctx"] >= estimate
    assert seen["options"]["num_ctx"] <= cand.context_window
    assert f"num_ctx={seen['options']['num_ctx']}" in completion.notes


async def test_ollama_streaming_uses_the_same_sizing() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        body = "\n".join(
            json.dumps(line)
            for line in [
                {"message": {"content": "হ্যাঁ"}, "done": False},
                {"message": {"content": ""}, "done": True, "model": "qwen3:4b"},
            ]
        )
        return httpx.Response(200, content=body.encode())

    adapter = OllamaAdapter(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://t"),
        base_url="http://t",
    )
    cand = RouteCandidate(provider="ollama", model="qwen3:4b", context_window=16_384)
    request = _request(_bangla(5_000), max_output_tokens=512)
    async for _ in adapter.stream(cand, request):
        pass
    assert seen["options"]["num_ctx"] >= estimate_request_tokens(request)
