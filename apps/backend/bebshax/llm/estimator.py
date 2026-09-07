"""Deterministic pre-flight token estimation — no tokenizer dependency.

Script-aware: ASCII text is rated at chars/3.5 (English prose ≈ 4 chars/token,
code/JSON ≈ 2.5–3); every non-ASCII character counts as at least one token,
because byte-level BPE vocabularies have thin coverage of scripts like Bangla
(each character is 3 UTF-8 bytes and usually 1–3 tokens). Slight
over-estimation is the safe direction: it only steers routing toward roomier
models; it can never cause truncation. This is the ONE estimator — adapters
sizing a context (Ollama num_ctx) must use it, never a private heuristic.
"""

from __future__ import annotations

import math

from bebshax.llm.types import LLMRequest

CHARS_PER_TOKEN = 3.5  # ASCII rate
NON_ASCII_TOKENS_PER_CHAR = 1.0
PER_MESSAGE_OVERHEAD_TOKENS = 4  # role tags / message framing
DEFAULT_EXPECTED_OUTPUT_TOKENS = 1024
SAFETY_MARGIN = 0.10  # applied to the whole request estimate


def estimate_text_tokens(text: str) -> int:
    """Token estimate for one string (no message overhead, no margin)."""
    ascii_chars = len(text.encode("ascii", "ignore"))  # C-speed count of ASCII chars
    non_ascii_chars = len(text) - ascii_chars
    return math.ceil(
        ascii_chars / CHARS_PER_TOKEN + non_ascii_chars * NON_ASCII_TOKENS_PER_CHAR
    )


def expected_output_tokens(request: LLMRequest) -> int:
    return request.max_output_tokens or DEFAULT_EXPECTED_OUTPUT_TOKENS


def estimate_request_tokens(request: LLMRequest) -> int:
    """Whole-request estimate: input + per-message framing + expected output,
    plus a 10% safety margin."""
    input_tokens = sum(
        estimate_text_tokens(m.content) + PER_MESSAGE_OVERHEAD_TOKENS for m in request.messages
    )
    return math.ceil((input_tokens + expected_output_tokens(request)) * (1 + SAFETY_MARGIN))
