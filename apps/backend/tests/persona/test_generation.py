import pytest

from bebshax.llm import SingleAdapterLLMService, TaskType
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.persona.generation import PersonaEngine, PersonaGenerationFailed


def _engine(replies: list[str], evidence_store, critic: bool = False):
    adapter = FakeAdapter(
        [FakeRoute(candidate=RouteCandidate(provider="fake", model="m1"), replies=list(replies))]
    )
    llm = SingleAdapterLLMService(adapter)
    return PersonaEngine(llm, evidence_store, critic=critic), adapter


def _tasks(adapter) -> list[TaskType]:
    return [request.task for request in adapter.requests]


async def test_happy_path_single_generation_call(evidence_store, persona_json) -> None:
    engine, adapter = _engine([persona_json()], evidence_store)
    profile = await engine.generate("b1", "QuickBite", "Online food delivery in Dhaka")
    assert profile.name == "Rina Akter"
    assert profile.business_id == "b1"
    assert profile.generation_model == "m1"
    assert _tasks(adapter) == [TaskType.PERSONA_GENERATION]
    # bogus citation from the model was stripped and downgraded — never trusted
    late = next(a for a in profile.attributes if a.value == "late deliveries")
    assert late.provenance_class.value == "INFERRED"
    assert late.evidence_ids == []
    # evidence retrieved for the prompt is preserved on the profile
    assert profile.evidence, "expected dataset evidence attached"


async def test_schema_invalid_output_gets_one_refinement(evidence_store, persona_json) -> None:
    engine, adapter = _engine(["this is not json at all", persona_json()], evidence_store)
    profile = await engine.generate("b1", "QuickBite", "Online food delivery")
    assert profile.name == "Rina Akter"
    assert _tasks(adapter) == [TaskType.PERSONA_GENERATION, TaskType.PERSONA_REFINEMENT]


async def test_schema_invalid_twice_fails_explicitly(evidence_store) -> None:
    engine, adapter = _engine(["nope", "still nope"], evidence_store)
    with pytest.raises(PersonaGenerationFailed):
        await engine.generate("b1", "QuickBite", "Online food delivery")
    assert _tasks(adapter) == [TaskType.PERSONA_GENERATION, TaskType.PERSONA_REFINEMENT]


async def test_contradiction_triggers_refinement_then_succeeds(evidence_store, persona_json) -> None:
    bad = persona_json(age=20, occupation="retired CEO")
    engine, adapter = _engine([bad, persona_json()], evidence_store)
    profile = await engine.generate("b1", "QuickBite", "Online food delivery")
    assert profile.occupation == "university student"
    assert _tasks(adapter) == [TaskType.PERSONA_GENERATION, TaskType.PERSONA_REFINEMENT]


async def test_persistent_contradiction_fails_with_violations(evidence_store, persona_json) -> None:
    bad = persona_json(age=20, occupation="retired CEO")
    engine, _ = _engine([bad, bad], evidence_store)
    with pytest.raises(PersonaGenerationFailed) as exc:
        await engine.generate("b1", "QuickBite", "Online food delivery")
    assert exc.value.violations and exc.value.violations[0].code == "age_occupation"


async def test_warnings_are_recorded_not_fatal(evidence_store, persona_json) -> None:
    payload = persona_json(
        behaviors=[
            {
                "value": "syncs with clients on US Pacific time",
                "provenance": "SYNTHETIC",
                "evidence_ids": [],
            }
        ]
    )
    engine, _ = _engine([payload], evidence_store)
    profile = await engine.generate("b1", "QuickBite", "Online food delivery")
    assert any("timezone" in w for w in profile.warnings)


async def test_twenty_concurrent_generations_all_succeed(evidence_store, persona_json) -> None:
    """Brief acceptance: 20 parallel persona generations, end to end."""
    import asyncio

    engine, adapter = _engine([persona_json()] * 20, evidence_store)
    profiles = await asyncio.gather(
        *(engine.generate("b1", "QuickBite", "Online food delivery") for _ in range(20))
    )
    assert len(profiles) == 20
    assert all(p.name == "Rina Akter" for p in profiles)
    # distinct profiles — no cross-contamination between the gathered runs
    assert len({p.id for p in profiles}) == 20
    assert _tasks(adapter) == [TaskType.PERSONA_GENERATION] * 20


async def test_critic_issues_become_warnings(evidence_store, persona_json) -> None:
    engine, adapter = _engine(
        [persona_json(), '{"issues": ["stated savings goal conflicts with spending"]}'],
        evidence_store,
        critic=True,
    )
    profile = await engine.generate("b1", "QuickBite", "Online food delivery")
    assert any(w.startswith("critic:") for w in profile.warnings)
    assert _tasks(adapter) == [TaskType.PERSONA_GENERATION, TaskType.CRITIC]
