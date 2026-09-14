"""Provider account notices delivered as HTTP 200 completion text are failures, not answers.

Seen live (2026-09-14): Pollinations answered every interview turn with its
"API key ... reached its budget" notice; the text was persisted as the persona's
reply, written to memory and synthesized into insights.
"""

import pytest

from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.llm.validation import provider_notice_kind, validate_text

POLLINATIONS_BUDGET = (
    "The API key used for this request has reached its budget. Please [raise the key budget]"
    "(https://enter.pollinations.ai/edit-key?id=89idjaTSg2hI4YwZDuO8ZME5Ma6GrFps&ref=agent_key_budget), then try again.\n\n"
    "Topping up the wallet does not raise this limit. If this isn't your Pollinations account, "
    "contact whoever runs the app or service you're using."
)


def _request(**changes) -> LLMRequest:
    return LLMRequest(task=TaskType.PERSONA_RESPONSE, messages=[ChatMessage(role="user", content="How do you do laundry?")], **changes)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (POLLINATIONS_BUDGET, FailureKind.QUOTA_EXHAUSTED),
        ("Error: You exceeded your current quota, please check your plan and billing details.", FailureKind.QUOTA_EXHAUSTED),
        ("{\"error\": {\"message\": \"Incorrect API key provided: sk-abc. You can find your API key at ...\"}}", FailureKind.AUTH_INVALID),
        ("Rate limit reached for gpt-4o in organization org-123 on tokens per min.", FailureKind.RATE_LIMITED),
    ],
)
def test_provider_notice_text_is_classified_and_rejected(text: str, kind: FailureKind) -> None:
    assert provider_notice_kind(text) is kind
    with pytest.raises(AttemptFailed) as failure:
        validate_text(text, _request(), "pollinations", "gpt-oss", finish_reason="stop")
    assert failure.value.kind is kind
    assert failure.value.provider == "pollinations"


@pytest.mark.parametrize(
    "text",
    [
        "I usually wash on Sundays because weekday budgets of time are tight; the hostel machine is always taken.",
        "Honestly I keep my API key for the campus portal in a notes app, and I'd pay 1200 BDT if pickup were reliable.",
        # A persona quoting the phrase deep in a long answer keeps its reply.
        ("x" * 400) + " The API key used for this request has reached its budget.",
        '{"summary": "Students report no time for laundry during exams", "insights": []}',
    ],
)
def test_ordinary_replies_are_not_mistaken_for_notices(text: str) -> None:
    assert provider_notice_kind(text) is None
    validate_text(text, _request(), "pollinations", "gpt-oss", finish_reason="stop")


def test_json_mode_notice_is_a_quota_failure_not_a_malformed_response() -> None:
    with pytest.raises(AttemptFailed) as failure:
        validate_text(POLLINATIONS_BUDGET, _request(json_mode=True), "pollinations", "gpt-oss")
    assert failure.value.kind is FailureKind.QUOTA_EXHAUSTED
