"""Deterministic pre-flight token estimation — no tokenizer dependency.

chars/3.5 is a conservative blended rate (English prose ≈ 4 chars/token,
code/JSON ≈ 2.5–3). Slight over-estimation is the safe direction: it only
steers routing toward roomier models; it can never cause truncation.
"""

from __future__ import annotations

from bebshax.llm.types import LLMRequest

CHARS_PER_TOKEN = 3.5
PER_MESSAGE_OVERHEAD_TOKENS = 4  # role tags / message framing
DEFAULT_EXPECTED_OUTPUT_TOKENS = 1024


def estimate_request_tokens(request: LLMRequest) -> int:
    input_tokens = sum(
        int(len(m.content) / CHARS_PER_TOKEN) + PER_MESSAGE_OVERHEAD_TOKENS
        for m in request.messages
    )
    return input_tokens + (request.max_output_tokens or DEFAULT_EXPECTED_OUTPUT_TOKENS)
