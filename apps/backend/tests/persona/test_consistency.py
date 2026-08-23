from bebshax.persona.consistency import check_consistency
from bebshax.persona.schema import PersonaAttribute, PersonaProfile


def _profile(**overrides) -> PersonaProfile:
    base = dict(
        business_id="b1",
        name="Test",
        age=30,
        occupation="engineer",
        location="Berlin, Germany",
        income_range="mid",
        education="MSc",
        description="a normal persona",
        attributes=[],
    )
    base.update(overrides)
    return PersonaProfile(**base)


def test_young_retired_ceo_is_an_error() -> None:
    violations = check_consistency(_profile(age=20, occupation="retired CEO"))
    assert any(v.code == "age_occupation" and v.severity == "error" for v in violations)


def test_student_stipend_with_frequent_luxury_is_flagged() -> None:
    profile = _profile(
        income_range="student stipend",
        attributes=[
            PersonaAttribute(
                key="purchase_behavior", value="frequent luxury designer handbag purchases"
            )
        ],
    )
    violations = check_consistency(profile)
    assert any(v.code == "income_luxury" and v.severity == "error" for v in violations)


def test_location_timezone_mismatch_is_a_warning() -> None:
    profile = _profile(
        location="Dhaka, Bangladesh",
        attributes=[
            PersonaAttribute(key="behavior", value="syncs with clients on US Pacific time")
        ],
    )
    violations = check_consistency(profile)
    assert any(v.code == "location_timezone" and v.severity == "warning" for v in violations)


def test_consistent_persona_has_no_violations() -> None:
    assert check_consistency(_profile()) == []
