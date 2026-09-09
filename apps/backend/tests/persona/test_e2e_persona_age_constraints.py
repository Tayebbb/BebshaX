from pathlib import Path

import pytest

from bebshax.api.errors import APIError
from bebshax.personas.ml_adapter import MLPersonaAdapter, build_business_context


@pytest.mark.parametrize("phrase", [
    "aged 25-45", "ages 25 to 45", "age 25\u201345", "AGED 25\u201445",
    "25-45 years old", "25 to 45 years old", "25\u201345 years old", "25\u201445 years old",
])
@pytest.mark.parametrize("field", ["description", "target_audience"])
def test_explicit_brief_age_ranges_bind_bounds(phrase: str, field: str) -> None:
    fields = {"description": "Food delivery for working couples", field: f"Working couples {phrase}"}
    context = build_business_context(**fields)
    assert (context.min_age, context.max_age) == (25, 45)
    assert getattr(context, field) == fields[field]


@pytest.mark.parametrize(("bounds", "expected"), [
    ({}, (25, 45)),
    ({"min_age": None, "max_age": None}, (25, 45)),
    ({"min_age": 30}, (30, 45)),
    ({"max_age": 40}, (25, 40)),
    ({"min_age": 30, "max_age": 40}, (30, 40)),
    ({"min_age": 18, "max_age": 95}, (25, 45)),
])
def test_structured_bounds_intersect_without_relaxing(bounds: dict, expected: tuple[int, int]) -> None:
    context = build_business_context(description="Food delivery for ages 25\u201345", **bounds)
    assert (context.min_age, context.max_age) == expected


@pytest.mark.parametrize("fields", [
    {"description": "Food delivery for ages 45-25"},
    {"description": "Food delivery for ages 17 to 45"},
    {"description": "Food delivery for ages 25\u201396"},
    {"target_audience": "96\u201495 years old"},
    {"target_audience": "45 to 25 years old"},
    {"description": "Food delivery for ages -5-45"},
    {"description": "Food delivery for ages 25-45", "min_age": 50},
    {"description": "Food delivery for ages 25-45", "max_age": 24},
    {"description": "Food delivery for ages 25-45", "target_audience": "ages 50-60"},
    {"description": "Food delivery for ages 25-45 and ages 50-60"},
    {"description": "Food delivery for ages 25-45", "min_age": 17},
])
def test_invalid_or_contradictory_ranges_fail_closed(fields: dict) -> None:
    with pytest.raises(APIError) as raised:
        build_business_context(**{"description": "Food delivery", **fields})
    assert raised.value.status_code == 422
    assert raised.value.error_code == "ml_persona_unsupported_context"


def test_description_and_audience_ranges_intersect() -> None:
    context = build_business_context(
        description="Food delivery for ages 25-45", target_audience="Workers aged 30 to 50",
    )
    assert (context.min_age, context.max_age) == (30, 45)


def test_non_age_numbers_and_source_biographies_do_not_bind_bounds() -> None:
    context = build_business_context(
        description="Food delivery for students costing $5\u201310 for 25-45 meals",
        target_audience="Working couples", role="Student aged 18-24",
        research=["Interviewees aged 65-75", "Source biography: 71-90 years old"],
        features=["Suitable for ages 18-24"], price_range="5-10",
    )
    assert (context.min_age, context.max_age) == (None, None)
    structured = build_business_context(description="Food delivery for students", min_age=31, max_age=54)
    assert (structured.min_age, structured.max_age) == (31, 54)


async def test_real_ml_selection_obeys_brief_and_exhaustion(ml_artifact: Path, ml_training_records) -> None:
    context = build_business_context(
        description="Food delivery. Focus on working couples aged 25\u201345 in the United States",
    )
    adapter = MLPersonaAdapter(ml_artifact)
    eligible = {record.record_id for record in ml_training_records if 25 <= record.age <= 45}
    selections = await adapter.generate(context, len(eligible), seed=17)
    assert {selection.record.record_id for selection in selections} == eligible
    assert all(25 <= selection.record.age <= 45 for selection in selections)
    with pytest.raises(APIError) as raised:
        await adapter.generate(context, 1, exclude_ids=eligible)
    assert raised.value.status_code == 422
    assert raised.value.error_code == "ml_persona_unsupported_context"


@pytest.mark.parametrize(("phrase", "bounds", "status"), [
    ("aged 25\u201345", {}, 200),
    ("aged 25\u201445", {"min_age": 30, "max_age": 40}, 200),
    ("25 to 45 years old", {"min_age": 50}, 422),
    ("ages 45-25", {}, 422),
    ("ages 17-45", {}, 422),
    ("aged 90-95", {}, 422),
])
async def test_study_api_binds_age_before_real_ml_selection(
    ml_api_app, ml_auth_headers, ml_study: str, phrase: str, bounds: dict, status: int,
) -> None:
    from bebshax.db.models import Studies

    async with ml_api_app.app.state.db_sessionmaker() as session:
        study = await session.get(Studies, ml_study)
        study.target_audience = ""
        await session.commit()

    response = ml_api_app.post("/api/study/generate-personas", headers=ml_auth_headers, json={
        "study_id": ml_study,
        "study_prompt": f"Food delivery. Focus on working couples {phrase} in the United States",
        "roles": [{
            "id": "couples", "role": "Working couples", "description": "Meal and work planning",
            "count": 2, "selected": True, **bounds,
        }],
    })
    assert response.status_code == status, response.text
    if status == 200:
        personas = response.json()["personas"]
        assert len(personas) == 2
        minimum = max(25, bounds.get("min_age", 25))
        maximum = min(45, bounds.get("max_age", 45))
        assert all(minimum <= persona["age"] <= maximum for persona in personas)
    else:
        assert response.json()["error_code"] == "ml_persona_unsupported_context"
    assert not ml_api_app.app.state.ml_test_llm.calls