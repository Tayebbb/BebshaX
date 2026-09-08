"""The report's output reservation must keep a typical report request on a
local context rung the 4 GB GPU can actually allocate.

Live finding (business-matrix run, 2026-09-08): with ``max_output_tokens=8000``
a ~1.1k-token report prompt estimated to ~10.1k tokens, the Ollama adapter
chose the 16384 rung, and all four local models failed with
``memory layout cannot be allocated`` / ``llama runner process has terminated``
-> HTTP 503 for 3 of 8 businesses once the free tiers were exhausted. The
14 reports that did complete peaked at 2,577 output tokens.
"""

from bebshax.llm.adapters.ollama_adapter import _ladder_rung
from bebshax.llm.estimator import estimate_request_tokens
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.research.report_service import REPORT_MAX_OUTPUT_TOKENS

LARGEST_OBSERVED_REPORT_REPLY_TOKENS = 2577
# The 14 live report prompts measured 904-1,448 input tokens; take the top end.
TYPICAL_REPORT_PROMPT_CHARS = 1448 * 4


def _report_request(prompt_chars: int) -> LLMRequest:
    return LLMRequest(
        task=TaskType.REPORT_GENERATION,
        messages=[
            ChatMessage(role="system", content="s" * 600),
            ChatMessage(role="user", content="x" * prompt_chars),
        ],
        json_mode=True,
        max_output_tokens=REPORT_MAX_OUTPUT_TOKENS,
    )


def test_typical_report_request_lands_on_the_8k_local_rung():
    rung = _ladder_rung(estimate_request_tokens(_report_request(TYPICAL_REPORT_PROMPT_CHARS)))
    assert rung <= 8192, f"report request would need num_ctx={rung}; 16k is not allocatable on the 4 GB local tier"


def test_reservation_keeps_headroom_over_the_largest_observed_reply():
    assert REPORT_MAX_OUTPUT_TOKENS >= LARGEST_OBSERVED_REPORT_REPLY_TOKENS * 1.5


def test_reservation_is_below_the_value_that_forced_16k():
    assert REPORT_MAX_OUTPUT_TOKENS < 8000
