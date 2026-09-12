"""Script-aware token estimation preserves complete English and Bangla inputs."""
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
