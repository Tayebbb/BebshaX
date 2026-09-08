"""Insight persistence never fails a finished interview.

Observed live on Postgres: the synthesis model wrote a free-text ``type`` for an
insight, ``InterviewInsights.type`` is String(64), asyncpg raised
StringDataRightTruncationError, the exception escaped ``complete()`` and the
batch job marked the interview FAILED although every turn was stored. SQLite
(the unit-test dialect) never enforces varchar lengths, so nothing caught it.

Only model-supplied LABELS are coerced to the column types; content is kept.
"""

import json

import pytest
from sqlalchemy import select

from bebshax.interview import engine as engine_module
from bebshax.interview.engine import (
    INSIGHT_TITLE_MAX_LEN,
    INSIGHT_TYPE_FALLBACK,
    INSIGHT_TYPE_MAX_LEN,
    InterviewEngine,
    coerce_insight_labels,
)
from bebshax.interview.orm import Conversations, InterviewInsights

_LONG_TYPE = (
    "Pain point: the persona is frustrated by late deliveries and hidden fees, "
    "which makes her compare prices across three apps every single evening"
)


# --- pure helper -------------------------------------------------------------


def test_long_free_text_type_becomes_a_bounded_snake_slug():
    labels = coerce_insight_labels({"type": _LONG_TYPE, "title": "t", "description": "d"})
    slug = labels["type"]
    assert len(slug) <= INSIGHT_TYPE_MAX_LEN == 64
    assert slug == slug.lower() and " " not in slug and ":" not in slug
    assert slug.startswith("pain_point_the_persona_is_frustrated")
    assert "__" not in slug and not slug.endswith("_")


def test_short_types_are_only_normalised():
    assert coerce_insight_labels({"type": "pain_point", "title": "t"})["type"] == "pain_point"
    assert coerce_insight_labels({"type": " Decision Factor ", "title": "t"})["type"] == "decision_factor"


@pytest.mark.parametrize("raw_type", ["", None, "   ", "!!!", "—"])
def test_empty_type_falls_back_to_the_catch_all_category_not_a_dropped_insight(raw_type):
    labels = coerce_insight_labels({"type": raw_type, "title": "Keep me", "description": "d"})
    assert labels["type"] == INSIGHT_TYPE_FALLBACK == "unresolved_question"
    assert labels["title"] == "Keep me"


def test_long_title_is_cut_at_a_word_boundary_and_every_word_survives_in_description():
    words = [f"word{i}" for i in range(60)]  # ~420 chars
    long_title = " ".join(words)
    labels = coerce_insight_labels({"type": "need", "title": long_title, "description": "The body."})

    assert len(labels["title"]) <= INSIGHT_TITLE_MAX_LEN == 256
    assert long_title.startswith(labels["title"])
    # Cut on a boundary: the stored title ends with a complete word.
    assert labels["title"].split()[-1] in words
    # Nothing lost: the full title leads the description, the body follows.
    assert labels["description"].startswith(long_title)
    assert labels["description"].endswith("The body.")
    for w in words:
        assert w in labels["description"]


def test_long_title_without_description_becomes_the_description():
    long_title = "x" * 300
    labels = coerce_insight_labels({"type": "need", "title": long_title, "description": None})
    assert labels["title"] == "x" * 256  # single token: hard cut is the only option
    assert labels["description"] == long_title


def test_short_title_and_description_are_untouched():
    labels = coerce_insight_labels({"type": "pricing", "title": "  Ceiling at 400 BDT ", "description": " body "})
    assert labels["title"] == "Ceiling at 400 BDT" and labels["description"] == "body"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("high", 0.0), (None, 0.0), ("0.9", 0.9), (0.45, 0.45), (1.7, 1.0), (-3, 0.0), (True, 0.0), (float("nan"), 0.0)],
)
def test_confidence_is_a_finite_unit_float_or_unmeasured(raw, expected):
    assert coerce_insight_labels({"type": "need", "title": "t", "confidence": raw})["confidence"] == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(["2", 3, None], [2, 3]), ([1.0, "x", True, 2.5], [1]), (4, [4]), (None, []), ("2", [2])],
)
def test_supporting_turn_numbers_keep_only_integers(raw, expected):
    assert coerce_insight_labels({"type": "need", "title": "t", "supporting_turn_numbers": raw})["supporting_turn_numbers"] == expected


# --- engine level ------------------------------------------------------------


def _synthesis(insights: list[dict]) -> str:
    return json.dumps(
        {
            "summary": "Rina compares prices nightly and abandons carts over delivery fees.",
            "key_findings": ["Delivery fees are the decisive objection."],
            "insights": insights,
        }
    )


async def test_complete_stores_an_insight_whose_type_overflows_the_column(
    session_maker, stored_persona, memory_service, llm_factory
):
    llm, adapter = llm_factory(
        [
            "Honestly the delivery fee decides it for me.",
            _synthesis(
                [
                    {
                        "type": _LONG_TYPE,
                        "title": "Delivery fees decide the order",
                        "description": "She abandons the cart whenever the fee exceeds the meal discount.",
                        "supporting_turn_numbers": ["2"],
                        "confidence": "high",
                    }
                ]
            ),
        ]
    )
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Pricing objections")
    await engine.ask(conversation.id, "What decides whether you order?")

    synthesis = await engine.complete(conversation.id)

    assert synthesis["status"] == "completed" and synthesis["source"] == "llm"
    assert synthesis["insights_dropped"] == 0
    assert len(synthesis["structured_insights"]) == 1
    stored = synthesis["structured_insights"][0]
    assert len(stored["type"]) <= 64 and stored["type"].startswith("pain_point_")
    assert stored["supporting_turn_numbers"] == [2] and stored["confidence"] == 0.0

    async with session_maker() as session:
        rows = list(
            (await session.execute(select(InterviewInsights).where(InterviewInsights.interview_id == conversation.id))).scalars()
        )
        assert len(rows) == 1
        assert rows[0].type == stored["type"] and len(rows[0].type) <= 64
        assert rows[0].title == "Delivery fees decide the order"
        conv = await session.get(Conversations, conversation.id)
        assert conv.status == "completed"
        # The model's own (uncoerced) insight text stays on the conversation as JSON.
        assert conv.structured_insights[0]["type"] == _LONG_TYPE


async def test_a_row_the_database_rejects_is_dropped_visibly_and_the_interview_still_completes(
    session_maker, stored_persona, memory_service, llm_factory, monkeypatch
):
    """Defence in depth: even a row the coercion did not foresee must not fail
    the interview. One insight is made to violate NOT NULL (description); the
    other is stored, the drop is counted, the conversation is completed."""
    real = engine_module.coerce_insight_labels

    def _one_bad_row(ins):
        labels = real(ins)
        if ins.get("title") == "BAD":
            labels["description"] = None  # NOT NULL on InterviewInsights.description
        return labels

    monkeypatch.setattr(engine_module, "coerce_insight_labels", _one_bad_row)

    llm, _ = llm_factory(
        [
            "Late deliveries are my main frustration.",
            _synthesis(
                [
                    {"type": "pain_point", "title": "BAD", "description": "x", "supporting_turn_numbers": [2], "confidence": 0.8},
                    {"type": "pain_point", "title": "Late deliveries", "description": "Arrives cold.", "supporting_turn_numbers": [2], "confidence": 0.7},
                ]
            ),
        ]
    )
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Pain points")
    await engine.ask(conversation.id, "What frustrates you most?")

    synthesis = await engine.complete(conversation.id)  # must not raise

    assert synthesis["status"] == "completed"
    assert synthesis["insights_dropped"] == 1
    assert [i["title"] for i in synthesis["structured_insights"]] == ["Late deliveries"]

    async with session_maker() as session:
        rows = list(
            (await session.execute(select(InterviewInsights).where(InterviewInsights.interview_id == conversation.id))).scalars()
        )
        assert [r.title for r in rows] == ["Late deliveries"]
        conv = await session.get(Conversations, conversation.id)
        assert conv.status == "completed" and conv.summary.startswith("Rina compares prices")
