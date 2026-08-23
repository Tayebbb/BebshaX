from bebshax.persona.schema import EvidenceItem, PersonaAttribute, PersonaProfile, ProvenanceClass
from bebshax.persona.store import (
    create_business,
    get_business,
    list_businesses,
    load_persona,
    save_persona,
)


def _profile(business_id: str) -> PersonaProfile:
    evidence = EvidenceItem(source="personahub_sample", text="a student ordering food", relevance=0.9)
    return PersonaProfile(
        business_id=business_id,
        name="Rina",
        age=24,
        occupation="student",
        location="Dhaka",
        income_range="stipend",
        education="BSc",
        description="desc",
        warnings=["minor note"],
        attributes=[
            PersonaAttribute(
                key="goal",
                value="cheap meals",
                provenance_class=ProvenanceClass.OBSERVED,
                evidence_ids=[evidence.id],
            ),
            PersonaAttribute(key="pain_point", value="late delivery"),
        ],
        evidence=[evidence],
    )


async def test_business_create_and_list(async_session) -> None:
    business = await create_business(async_session, "QuickBite", "food delivery")
    assert await get_business(async_session, business.id) is not None
    assert any(b.id == business.id for b in await list_businesses(async_session))


async def test_persona_round_trip(async_session) -> None:
    business = await create_business(async_session, "QuickBite", "food delivery")
    original = _profile(business.id)
    await save_persona(async_session, original)

    loaded = await load_persona(async_session, original.id)
    assert loaded is not None
    assert loaded.name == original.name
    assert loaded.age == 24 and loaded.occupation == "student"
    assert loaded.warnings == ["minor note"]
    assert {a.key for a in loaded.attributes} == {"goal", "pain_point"}
    goal = next(a for a in loaded.attributes if a.key == "goal")
    assert goal.provenance_class == ProvenanceClass.OBSERVED
    assert goal.evidence_ids == [original.evidence[0].id]
    assert loaded.evidence[0].text == "a student ordering food"


async def test_load_missing_persona_returns_none(async_session) -> None:
    assert await load_persona(async_session, "nope") is None
