"""The dashboard progress line is derived from study state, never a stored string."""

from __future__ import annotations

from bebshax.api.studies import _study_summary_text
from bebshax.db.models import Studies


def _study(**overrides: object) -> Studies:
    values: dict[str, object] = {"status": "draft", "step": 1, "persona_count": 0, "findings": None}
    values.update(overrides)
    return Studies(id="study_x", title="t", type="interviews", goal="demand_validation", **values)


def test_fresh_study_reads_just_created() -> None:
    assert _study_summary_text(_study()) == "Just created • Step 1 Context"


def test_in_progress_study_reports_step_and_persona_count() -> None:
    assert _study_summary_text(_study(status="in_progress", step=4, persona_count=3)) == (
        "In Progress • Step 4 Interviews • 3 synthetic personas"
    )
    assert _study_summary_text(_study(status="in_progress", step=2)) == "In Progress • Step 2 Personas • No personas yet"
    assert _study_summary_text(_study(status="in_progress", step=1, persona_count=1)) == (
        "In Progress • Step 1 Context • 1 synthetic persona"
    )


def test_completed_study_never_claims_just_created() -> None:
    finished = _study(status="completed", step=5, persona_count=3, findings={"executive_summary": "x"})
    assert _study_summary_text(finished) == "Completed • Decision report ready • 3 synthetic personas"
    assert _study_summary_text(_study(status="completed", step=5, persona_count=2)) == (
        "Completed • Report pending • 2 synthetic personas"
    )


def test_unknown_step_stays_numeric() -> None:
    assert _study_summary_text(_study(status="in_progress", step=9, persona_count=0)) == (
        "In Progress • Step 9 • No personas yet"
    )
