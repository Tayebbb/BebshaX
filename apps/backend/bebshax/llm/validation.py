"""Mechanical completion validation, separate from semantic answer quality."""

from __future__ import annotations

import json
import re

from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.json_utils import parse_llm_json, strip_md_fences
from bebshax.llm.types import LLMRequest, TokenUsage

# Some free providers answer HTTP 200 with an account notice in place of model
# output (seen live: Pollinations "API key ... reached its budget"). Matched only
# against the opening of the reply so a persona discussing billing is untouched.
_PROVIDER_NOTICE_SIGNATURES: tuple[tuple[re.Pattern[str], FailureKind], ...] = (
    (re.compile(r"\bAPI key\b.{0,80}\b(reached its budget|budget has been reached|out of credits?|insufficient (credits?|balance|funds))", re.I | re.S), FailureKind.QUOTA_EXHAUSTED),
    (re.compile(r"\b(raise the key budget|insufficient_quota|exceeded your current quota|billing hard limit|quota exceeded for)\b", re.I), FailureKind.QUOTA_EXHAUSTED),
    (re.compile(r"\b(incorrect API key provided|invalid_api_key|invalid api key|api key (is )?(invalid|revoked|expired)|authentication (error|failed):)", re.I), FailureKind.AUTH_INVALID),
    (re.compile(r"\b(rate limit (reached|exceeded) for|too many requests, please try again)", re.I), FailureKind.RATE_LIMITED),
)
_NOTICE_WINDOW = 320


def provider_notice_kind(text: str) -> FailureKind | None:
    """Failure kind when the reply is a provider account notice, else None."""
    head = text.lstrip()[:_NOTICE_WINDOW]
    for pattern, kind in _PROVIDER_NOTICE_SIGNATURES:
        if pattern.search(head):
            return kind
    return None


def validate_text(
    text: str, request: LLMRequest, provider: str, model: str,
    *, finish_reason: str | None = None,
) -> None:
    if finish_reason is not None and (
        not isinstance(finish_reason, str) or finish_reason not in {
            "stop", "STOP", "end_turn", "stop_sequence", "eos_token",
            "length", "max_tokens", "MAX_TOKENS", "content_filter", "SAFETY",
            "RECITATION", "tool_calls", "function_call",
        }
    ):
        raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, provider, model, "invalid finish_reason metadata")
    if finish_reason in {"length", "max_tokens", "MAX_TOKENS"}:
        raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, provider, model, "output truncated: finish_reason=" + finish_reason)
    if finish_reason in {"content_filter", "SAFETY", "RECITATION"}:
        raise AttemptFailed(FailureKind.CONTENT_REFUSAL, provider, model, "provider refused completion")
    if finish_reason in {"tool_calls", "function_call"}:
        raise AttemptFailed(FailureKind.CAPABILITY_UNSUPPORTED, provider, model, "tool execution contract is unavailable")
    if not isinstance(text, str) or not text.strip():
        raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, provider, model, "empty response")
    notice = provider_notice_kind(text)
    if notice is not None:
        raise AttemptFailed(notice, provider, model, "provider returned an account notice instead of a completion")
    if request.json_mode:
        try:
            cleaned = strip_md_fences(text)
            first = next((index for index, char in enumerate(cleaned) if char in "{["), -1)
            if first < 0 or cleaned[first] != "{":
                raise ValueError("expected an object root")
            depth = 0
            quoted = False
            escaped = False
            closed = False
            for char in cleaned[first:]:
                if closed:
                    if char in "{}[]":
                        raise ValueError("extra structured suffix")
                    continue
                if quoted:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        quoted = False
                elif char == '"':
                    quoted = True
                elif char in "{[":
                    depth += 1
                elif char in "}]":
                    depth -= 1
                    closed = depth == 0
            if not closed or quoted:
                raise ValueError("unfinished structured response")
            parsed = parse_llm_json(text)
            if not isinstance(parsed, dict):
                raise ValueError("expected a JSON object")
            json.dumps(parsed, allow_nan=False)
        except (ValueError, TypeError) as exc:
            raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, provider, model, "response must contain a complete JSON object") from exc


def validated_usage(data: dict, provider: str, model: str) -> TokenUsage:
    values = [data.get("prompt_tokens"), data.get("completion_tokens")]
    if any(value is not None and (type(value) is not int or value < 0) for value in values):
        raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, provider, model, "invalid token usage")
    return TokenUsage(input_tokens=values[0], output_tokens=values[1])