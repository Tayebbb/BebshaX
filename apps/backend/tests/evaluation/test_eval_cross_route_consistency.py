"""Cross-route persona consistency: pure metrics on hand-built answers, the
FakeAdapter-backed runner, and the CLI's offline (--fake) pipeline check."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from bebshax.evaluation.cross_route_consistency import (
    PERSONA_BANK,
    QUESTION_BANK,
    REPORT_KIND,
    AnswerRow,
    PersonaFacts,
    Question,
    Route,
    agreement_metrics,
    bootstrap_ci,
    compute_report,
    cosine,
    extract_age,
    extract_bdt_amounts,
    fact_retention,
    numeric_divergence,
    run_cross_route_eval,
    scripted_router,
    to_markdown,
)
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.embeddings import HashEmbedding
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.failures import FailureKind
from bebshax.llm.router import PoolRouter

NUSRAT = PersonaFacts("p1", "Nusrat Jahan", 24, "third-year BBA undergraduate", "Mohammadpur, Dhaka", 300)
RAFIQ = PersonaFacts("p2", "Rafiqul Islam", 34, "coaching-centre teacher", "Khilgaon, Dhaka", 500)
Q_ID = Question("q_identity", "Introduce yourself.", ("name", "age", "occupation"))
Q_LOC = Question("q_location", "Where do you live?", ("location",))
Q_BUDGET = Question("q_budget", "How much per month, in taka?", ("budget",))
ROUTE_A = Route("fakeA", "m1")
ROUTE_B = Route("fakeB", "m2")


# ------------------------------------------------------------ extraction ---


def test_fact_retention_is_one_when_every_probed_fact_is_restated():
    answer = "I'm Nusrat, 24 years old, a third-year BBA undergraduate at a Dhaka university."
    assert fact_retention(NUSRAT, answer, Q_ID.probes) == {"name": True, "age": True, "occupation": True}


def test_fact_retention_is_zero_when_identity_drifts():
    answer = "I'm Karim, 41 years old, and I drive a rickshaw in Chittagong."
    assert fact_retention(NUSRAT, answer, Q_ID.probes) == {"name": False, "age": False, "occupation": False}
    assert fact_retention(NUSRAT, answer, ("location",)) == {"location": False}


def test_fact_retention_only_reports_probed_facts():
    assert fact_retention(NUSRAT, "I live in Mohammadpur.", ("location",)) == {"location": True}
    assert fact_retention(NUSRAT, "anything", ()) == {}


def test_extract_age_handles_common_phrasings_and_rejects_noise():
    assert extract_age("I am 24 years old") == 24
    assert extract_age("a 34-year-old teacher") == 34
    assert extract_age("I'm 19 and study for HSC") == 19
    assert extract_age("I pay 300 taka a month") is None  # money is not an age


def test_numeric_divergence_measures_distance_to_budget_or_is_none():
    assert numeric_divergence(NUSRAT, "About ৳300 per month would be fine.") == 0.0
    assert numeric_divergence(NUSRAT, "I could pay 500 taka per month.") == 200.0
    assert numeric_divergence(NUSRAT, "I never thought about it.") is None
    assert numeric_divergence(PersonaFacts("x", "A B", 30, "clerk", "Dhaka"), "৳300 per month") is None
    assert extract_bdt_amounts("nothing here") == []


# -------------------------------------------------------------- metrics ---


def _row(persona: PersonaFacts, question: Question, route: Route, answer: str, **kw) -> AnswerRow:
    return AnswerRow(
        persona_id=persona.persona_id,
        question_id=question.id,
        route_requested=route.label,
        repeat=1,
        answer=answer,
        success=True,
        served_by_provider=route.provider,
        served_by_model=route.model,
        route_honoured=True,
        attempts=1,
        retention=fact_retention(persona, answer, question.probes),
        **kw,
    )


async def test_agreement_ratio_exceeds_one_when_persona_signal_dominates():
    rows = [
        _row(NUSRAT, Q_ID, ROUTE_A, "I'm Nusrat Jahan, 24 years old, a third-year BBA undergraduate in Dhaka."),
        _row(NUSRAT, Q_ID, ROUTE_B, "I am Nusrat Jahan, 24 years old, a BBA undergraduate in Dhaka, third year."),
        _row(RAFIQ, Q_ID, ROUTE_A, "I'm Rafiqul Islam, 34 years old, a coaching-centre teacher in Khilgaon."),
        _row(RAFIQ, Q_ID, ROUTE_B, "I am Rafiqul Islam, 34, teaching at a coaching centre in Khilgaon, Dhaka."),
    ]
    vectors = dict(enumerate(await HashEmbedding().embed([r.answer for r in rows])))
    agree = agreement_metrics(rows, vectors)
    assert agree["n_same_persona_pairs"] == 2 and agree["n_cross_persona_pairs"] == 4
    assert agree["cross_route_agreement"] > agree["baseline_agreement"]
    assert agree["agreement_ratio"] > 1.0


async def test_agreement_ratio_below_one_when_routes_override_the_persona():
    # Both routes ignore the persona and answer with a route-specific boilerplate.
    boiler_a = "As an AI language model I cannot have a name or an age, but I can help you plan."
    boiler_b = "Sure! Here is a fun fact about study planning apps and productivity."
    rows = [
        _row(NUSRAT, Q_ID, ROUTE_A, boiler_a),
        _row(NUSRAT, Q_ID, ROUTE_B, boiler_b),
        _row(RAFIQ, Q_ID, ROUTE_A, boiler_a),
        _row(RAFIQ, Q_ID, ROUTE_B, boiler_b),
    ]
    vectors = dict(enumerate(await HashEmbedding().embed([r.answer for r in rows])))
    agree = agreement_metrics(rows, vectors)
    assert agree["agreement_ratio"] < 1.0


def test_agreement_is_none_without_comparable_pairs():
    rows = [_row(NUSRAT, Q_ID, ROUTE_A, "solo answer")]
    agree = agreement_metrics(rows, {0: [1.0, 0.0]})
    assert agree["cross_route_agreement"] is None and agree["agreement_ratio"] is None


async def test_agreement_pairs_by_served_route_not_requested_route():
    """Preference is advisory: when every answer was served by ONE model, the
    metric must say 'not measurable' instead of calling within-model
    repeatability a cross-route result (observed on the first real run)."""
    rows = [
        _row(NUSRAT, Q_ID, ROUTE_A, "I'm Nusrat Jahan, 24, a BBA undergraduate."),
        # requested route B, but route A actually answered
        _row(NUSRAT, Q_ID, ROUTE_B, "I am Nusrat Jahan, 24, a BBA undergraduate."),
        _row(RAFIQ, Q_ID, ROUTE_A, "I'm Rafiqul Islam, 34, a coaching-centre teacher."),
        _row(RAFIQ, Q_ID, ROUTE_B, "I am Rafiqul Islam, 34, a coaching-centre teacher."),
    ]
    for r in rows:
        r.served_by_provider, r.served_by_model = ROUTE_A.provider, ROUTE_A.model
        r.route_honoured = Route.parse(r.route_requested).provider == ROUTE_A.provider
    vectors = dict(enumerate(await HashEmbedding().embed([r.answer for r in rows])))
    agree = agreement_metrics(rows, vectors)
    assert agree["distinct_served_routes"] == [ROUTE_A.label]
    assert agree["cross_route_agreement"] is None and agree["n_same_persona_pairs"] == 0
    assert "not measurable" in agree["agreement_note"]
    assert agree["baseline_agreement"] is not None  # cross-persona baseline still real


def test_cosine_basics():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine([0, 0], [1, 1]) == 0.0


def test_bootstrap_ci_contains_the_mean_and_is_deterministic():
    values = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 0.0]
    mean = sum(values) / len(values)
    lo, hi = bootstrap_ci(values, seed=7)
    assert lo <= mean <= hi
    assert lo < hi
    assert bootstrap_ci(values, seed=7) == (lo, hi)
    assert bootstrap_ci([0.5, 0.5, 0.5], seed=1) == (0.5, 0.5)
    assert bootstrap_ci([], seed=1) is None


async def test_compute_report_aggregates_and_cis_bracket_means():
    rows = [
        _row(NUSRAT, Q_ID, ROUTE_A, "I'm Nusrat, 24 years old, a BBA undergraduate."),
        _row(NUSRAT, Q_ID, ROUTE_B, "I'm Nusrat, 24 years old, a BBA undergraduate."),
        _row(RAFIQ, Q_ID, ROUTE_A, "I'm Rafiqul, a coaching-centre teacher."),  # age missing
        _row(RAFIQ, Q_ID, ROUTE_B, "I'm Rafiqul, 34 years old, a coaching-centre teacher."),
        _row(NUSRAT, Q_BUDGET, ROUTE_A, "৳300 per month.", numeric_divergence=0.0),
        _row(NUSRAT, Q_BUDGET, ROUTE_B, "৳400 per month.", numeric_divergence=100.0),
    ]
    report = await compute_report([NUSRAT, RAFIQ], [Q_ID, Q_BUDGET], [ROUTE_A, ROUTE_B], rows, seed=3)
    assert report.kind == REPORT_KIND and report.simulated is False
    assert report.n_rows == 6 and report.n_served == 6 and report.n_failed == 0
    assert report.n_probed_facts == 12 and report.identity_fact_retention == pytest.approx(11 / 12)
    lo, hi = report.identity_fact_retention_ci95
    assert lo <= report.identity_fact_retention <= hi
    assert report.numeric_divergence_mean_bdt == 50.0 and report.n_numeric_probes == 2
    assert report.per_route[ROUTE_A.label]["identity_fact_retention"] == pytest.approx(5 / 6)
    assert report.per_route[ROUTE_B.label]["identity_fact_retention"] == 1.0
    assert report.embedding_space == HashEmbedding.space
    assert report.contradiction_count == 0  # engine detector ran over the sequences
    assert "_detect_contradiction" in report.contradiction_note
    md = to_markdown(report)
    assert "identity_fact_retention" in md and "not measured" not in md.split("| numeric_divergence")[0]
    assert json.dumps(report.to_dict())  # JSON-serialisable


# --------------------------------------------------------------- runner ---


def _two_route_router(fail_first_on_b: bool = False) -> PoolRouter:
    cand_a = RouteCandidate(provider="fakeA", model="m1")
    cand_b = RouteCandidate(provider="fakeB", model="m2")
    replies_a = ["I'm Nusrat Jahan, 24 years old, a BBA undergraduate."] * 8
    replies_b = ["I'm Nusrat Jahan, 24 years old, a BBA undergraduate (B)."] * 8
    b_behaviors = [FailureKind.RATE_LIMITED] if fail_first_on_b else []
    adapter = FakeAdapter(
        [FakeRoute(cand_a, replies=replies_a), FakeRoute(cand_b, behaviors=b_behaviors, replies=replies_b)]
    )
    return PoolRouter({"openrouter": FakeAdapter([]), "freellmpool": adapter, "ollama": FakeAdapter([])})


async def test_runner_produces_a_row_for_every_persona_question_route():
    routes = [ROUTE_A, ROUTE_B]
    report = await run_cross_route_eval(
        _two_route_router(), [NUSRAT, RAFIQ], [Q_ID, Q_LOC], routes, repeats=1, seed=1, simulated=True
    )
    assert report.n_rows == 2 * 2 * 2 and report.n_failed == 0
    keys = {(r["persona_id"], r["question_id"], r["route_requested"]) for r in report.rows}
    assert keys == {
        (p.persona_id, q.id, r.label) for p in (NUSRAT, RAFIQ) for q in (Q_ID, Q_LOC) for r in routes
    }
    # Honest provenance: every row names the route that actually served it.
    for row in report.rows:
        assert row["served_by_provider"] in ("fakeA", "fakeB")
        assert row["route_served"] == row["route_requested"] and row["route_honoured"] is True
        assert row["attempts"] == 1 and row["request_id"]
    assert report.per_route[ROUTE_B.label]["served_routes"] == {"fakeB/m2": 4}
    assert report.simulated is True


async def test_runner_records_fallback_honestly_when_the_requested_route_fails():
    report = await run_cross_route_eval(
        _two_route_router(fail_first_on_b=True), [NUSRAT], [Q_ID], [ROUTE_A, ROUTE_B], seed=1
    )
    b_row = next(r for r in report.rows if r["route_requested"] == ROUTE_B.label)
    assert b_row["success"] is True
    assert b_row["route_served"] == "fakeA/m1"  # preference is advisory — fallback served
    assert b_row["route_honoured"] is False and b_row["attempts"] == 2
    assert report.per_route[ROUTE_B.label]["route_honoured"] == 0
    assert report.per_route[ROUTE_B.label]["served_routes"] == {"fakeA/m1": 1}


async def test_runner_keeps_failed_answers_as_rows():
    cand_a = RouteCandidate(provider="fakeA", model="m1")
    # TIMEOUT: no cooldown, so the single route fails once and serves the next request.
    adapter = FakeAdapter(
        [FakeRoute(cand_a, behaviors=[FailureKind.TIMEOUT], reply="I'm Nusrat, 24 years old, a BBA undergraduate.")]
    )
    router = PoolRouter({"openrouter": FakeAdapter([]), "freellmpool": adapter, "ollama": FakeAdapter([])})
    report = await run_cross_route_eval(router, [NUSRAT], [Q_ID], [ROUTE_A, ROUTE_B], seed=1)
    assert report.n_rows == 2 and report.n_served == 1 and report.n_failed == 1
    failed = next(r for r in report.rows if not r["success"])
    assert failed["error"].startswith("AllCandidatesFailed") and failed["attempts"] == 1
    assert report.identity_fact_retention == 1.0  # measured only over served rows


async def test_scripted_router_answers_from_the_identity_card_per_persona():
    routes = [ROUTE_A, ROUTE_B]
    report = await run_cross_route_eval(
        scripted_router(routes), list(PERSONA_BANK[:3]), list(QUESTION_BANK), routes, repeats=2, seed=42, simulated=True
    )
    assert report.n_rows == 3 * len(QUESTION_BANK) * 2 * 2 and report.n_failed == 0
    assert report.identity_fact_retention == 1.0
    assert report.numeric_divergence_mean_bdt == 0.0 and report.n_numeric_probes == 3 * 2 * 2
    assert report.agreement_ratio > 1.0
    assert report.contradiction_count == 0


# ------------------------------------------------------------------ CLI ---


def test_cli_fake_run_writes_json_and_markdown(tmp_path: Path):
    out = tmp_path / "cross_route_smoke.json"
    cmd = [
        sys.executable, "scripts/run_cross_route_eval.py", "--fake",
        "--personas", "2", "--questions", "2", "--routes", "fakeA/m1,fakeB/m2",
        "--repeats", "1", "--seed", "1", "--output", str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr
    assert "simulated=True" in proc.stdout
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["kind"] == REPORT_KIND and data["simulated"] is True
    assert data["n_rows"] == 2 * 2 * 2 and data["n_failed"] == 0
    assert any("SIMULATED" in note for note in data["notes"])
    md = out.with_suffix(".md")
    assert md.exists() and "Cross-route persona consistency" in md.read_text(encoding="utf-8")
