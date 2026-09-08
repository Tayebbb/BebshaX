"""Numeric self-consistency in the contradiction detector.

Live QA found a persona claiming "120 taka" per day for lunch in turn 1, then
"25,000 to 30,000 BDT on lunch per month" in turn 2 (~7x apart) — undetected.
The detector must compare the persona's own prior money-rate claims.
"""

from types import SimpleNamespace

from bebshax.interview.engine import (
    InterviewEngine,
    _extract_money_rates,
    _shares_spend_topic,
)


def _detector():
    # _detect_contradiction only reads its arguments; no engine wiring needed.
    return InterviewEngine.__new__(InterviewEngine)


def _persona(budget: int = 5000):
    return SimpleNamespace(commercial_profile={"monthly_budget_bdt": budget})


class TestExtractMoneyRates:
    def test_daily_rate_normalizes_to_monthly(self) -> None:
        rates = _extract_money_rates("it cost me around 120 taka, which is standard, yesterday")
        assert len(rates) == 1
        assert rates[0][0] == 120 * 30

    def test_monthly_rate_kept_as_is(self) -> None:
        rates = _extract_money_rates("i spend around 25,000 bdt on lunch per month")
        assert rates and rates[0][0] == 25000.0

    def test_bare_numbers_without_currency_are_ignored(self) -> None:
        assert _extract_money_rates("i wait 30 minutes every day for delivery") == []

    def test_number_without_period_cue_is_ignored(self) -> None:
        assert _extract_money_rates("the tv costs 45000 taka at the shop") == []


class TestLocaleAwareCurrencyCues:
    """Cue markers come from the persona's country — BD stays the default."""

    def test_dollar_amounts_count_for_us_personas(self) -> None:
        rates = _extract_money_rates("i spend about $45 per day on food", "US")
        assert rates and rates[0][0] == 45 * 30

    def test_small_amounts_use_locale_minimum(self) -> None:
        # $5/day is a real US money rate; 5 would be noise under the BDT floor
        rates = _extract_money_rates("coffee runs me $5 a day", "US")
        assert rates and rates[0][0] == 5 * 30

    def test_unknown_country_accepts_any_currency_cue(self) -> None:
        # No country is assumed: an unknown/absent country counts every currency
        # cue instead of silently defaulting to one locale.
        assert _extract_money_rates("i spend about $45 per day on food")[0][0] == 45 * 30
        assert _extract_money_rates("i spend about 450 taka per day on food", "XX")[0][0] == 450 * 30
        assert _extract_money_rates("i spend about 45 per day on food") == []  # no cue at all

    def test_dollar_amounts_do_not_count_for_bd_coded_personas(self) -> None:
        assert _extract_money_rates("i spend about $45 per day on food", "BD") == []

    def test_rupee_word_counts_for_in_personas(self) -> None:
        rates = _extract_money_rates("around 900 rupees a month for tiffin", "IN")
        assert rates and rates[0][0] == 900.0

    def test_taka_still_works_when_country_is_bd(self) -> None:
        rates = _extract_money_rates("i spend around 25,000 bdt on lunch per month", "BD")
        assert rates and rates[0][0] == 25000.0


class TestNumericContradiction:
    QUESTION = "How much do you spend on lunch?"
    TURN1 = (
        "Yesterday I grabbed biryani from the street vendor. It cost me around "
        "120 taka, which is pretty standard, and I ate at my desk."
    )
    TURN2 = (
        "I spend around 25,000 to 30,000 BDT on lunch per month, give or take. "
        "3,000 BDT a month for delivered meals sounds steep compared to that."
    )

    def test_detects_the_live_observed_contradiction(self) -> None:
        flagged, details, follow_up, confidence = _detector()._detect_contradiction(
            _persona(), self.QUESTION, self.TURN2, prior_persona_texts=[self.TURN1]
        )
        assert flagged is True
        assert "self-contradiction" in details
        assert follow_up and "closer to what you actually spend" in follow_up
        # deterministic rule → boolean fact; no invented probability attached
        assert confidence is None

    def test_consistent_claims_do_not_flag(self) -> None:
        consistent = "My lunch runs about 3,600 taka per month in total."
        flagged, *_ = _detector()._detect_contradiction(
            _persona(), self.QUESTION, consistent, prior_persona_texts=[self.TURN1]
        )
        assert flagged is False

    def test_no_prior_turns_never_flags(self) -> None:
        flagged, *_ = _detector()._detect_contradiction(
            _persona(), self.QUESTION, self.TURN2, prior_persona_texts=[]
        )
        assert flagged is False

    def test_unrelated_topics_are_not_compared(self) -> None:
        # Prior turn about lunch spend; new claim about rent — no shared spend
        # topic wording beyond generic, so magnitude gap alone must not flag.
        rent_reply = "My rent is 25,000 taka a month in Gulshan."
        flagged, *_ = _detector()._detect_contradiction(
            _persona(), "Where do you live?", rent_reply,
            prior_persona_texts=["Yesterday my ride was quick."],
        )
        assert flagged is False

    def test_restating_the_known_budget_is_not_a_spend_claim(self) -> None:
        """Observed in the first real cross-route run (llm7/codestral, 3/3 flags):
        'with a monthly budget of 800 BDT for apps and services I could spend
        around 200 BDT per month on this app' restates the persona's TOTAL budget
        and then allocates part of it — two different quantities, not a
        contradiction. Only genuine spend-vs-spend gaps may flag."""
        budget_reply = (
            "As a junior software developer with a monthly budget of 800 BDT for apps and "
            "services, I could potentially spend around 200 BDT per month on an app that plans my study."
        )
        pain_reply = (
            "With a monthly budget of 800 BDT for apps and services, the most frustrating part "
            "of organizing my week is balancing work and a limited budget."
        )
        det = _detector()
        flagged, *_ = det._detect_contradiction(
            _persona(800), "How much could you spend per month?", budget_reply, prior_persona_texts=[]
        )
        assert flagged is False
        flagged, *_ = det._detect_contradiction(
            _persona(800), "What is frustrating?", pain_reply, prior_persona_texts=[budget_reply]
        )
        assert flagged is False
        # …while a real 4x gap between two spend claims on the same topic still flags
        flagged, *_ = det._detect_contradiction(
            _persona(800), "How much for the app?",
            "I would spend around 900 BDT per month on the app.",
            prior_persona_texts=["I could spend around 200 BDT per month on an app that plans my study."],
        )
        assert flagged is True


def test_shares_spend_topic_requires_common_word() -> None:
    assert _shares_spend_topic("my lunch cost 120 taka", "lunch is 3000 bdt monthly")
    assert not _shares_spend_topic("my ride was late", "the weather is hot")


async def test_ask_persists_numeric_contradiction_metadata(
    session_maker, stored_persona, memory_service, llm_factory
) -> None:
    """End-to-end wiring: contradictory scripted replies across two turns must
    land as contradiction_detected=True in the second persona turn's metadata."""
    llm, _ = llm_factory([
        "Yesterday my lunch cost me around 120 taka from the street vendor.",
        "I spend around 25,000 bdt on lunch per month, give or take.",
    ])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "spend consistency check")
    await engine.ask(conversation.id, "What did lunch cost you yesterday?")
    await engine.ask(conversation.id, "How much do you spend on lunch monthly?")

    _, turns = await engine.transcript(conversation.id)
    persona_turns = [t for t in turns if t.role == "persona"]
    assert persona_turns[0].metadata_json["contradiction_detected"] is False
    second = persona_turns[1].metadata_json
    assert second["contradiction_detected"] is True
    assert "self-contradiction" in second["contradiction_details"]
