import asyncio
import json
from collections import Counter

import pytest
from sqlalchemy import select

from bebshax.api.limiter import limiter
from bebshax.auth.models import Users
from bebshax.db.models import DatasetPersonaRuns, DatasetSources, MarketSegments, PersonaGenerationRuns, Personas, Studies
from bebshax.llm.types import TaskType
from bebshax.personas.ml_adapter import MLPersonaAdapter


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    limiter._limiter.storage.reset()
    yield
    limiter._limiter.storage.reset()


def test_main_wires_local_adapter_without_eager_loading(ml_api_app) -> None:
    adapter = ml_api_app.app.state.persona_ml
    assert isinstance(adapter, MLPersonaAdapter)
    assert adapter._model is None
    assert ml_api_app.app.state.ml_test_llm.calls == []


@pytest.mark.parametrize("background", [False, True], ids=["sync", "job"])
async def test_repeated_study_generation_appends_distinct_sources_and_updates_active_count(
    ml_api_app, ml_auth_headers, ml_study, background,
) -> None:
    async def finish_jobs() -> None:
        await asyncio.gather(*tuple(ml_api_app.app.state.async_job_tasks))

    source_batches = []
    for generation_number in range(2):
        endpoint = f"/api/studies/{ml_study}/personas/generate"
        response = ml_api_app.post(
            f"{endpoint}/jobs" if background else endpoint,
            json={"target_count": 2}, headers=ml_auth_headers,
        )
        assert response.status_code == (202 if background else 201), response.text
        if background:
            ml_api_app.portal.call(finish_jobs)
            response = ml_api_app.get(
                f"{endpoint}/jobs/{response.json()['job_id']}", headers=ml_auth_headers,
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "completed", response.text
            result = response.json()["result"]
        else:
            result = response.json()
        assert result["run"]["generated_count"] == result["run"]["target_count"] == 2
        source_batches.append({
            persona["detailed_attributes"]["ml_provenance"]["record_id"]
            for persona in result["personas"]
        })
        assert len(source_batches[-1]) == 2
        async with ml_api_app.app.state.db_sessionmaker() as session:
            active = list((await session.scalars(select(Personas).where(
                Personas.study_id == ml_study, Personas.owner_id == "usr_test_fixture",
                Personas.status != "archived",
            ))).all())
            assert len(active) == (generation_number + 1) * 2
            assert (await session.get(Studies, ml_study)).persona_count == len(active)
    assert source_batches[0].isdisjoint(source_batches[1])
    assert ml_api_app.app.state.ml_test_llm.calls == []


async def test_repeated_business_generation_appends_distinct_source_profiles(
    ml_api_app, ml_auth_headers,
) -> None:
    business = ml_api_app.post(
        "/api/businesses", json={"name": "Meal Planner", "description": "Food delivery and study planning"},
        headers=ml_auth_headers,
    )
    assert business.status_code == 201, business.text
    business_id = business.json()["id"]
    personas = []
    for generation_number in range(2):
        response = ml_api_app.post(
            f"/api/businesses/{business_id}/personas", json={}, headers=ml_auth_headers,
        )
        assert response.status_code == 201, response.text
        personas.append(response.json())
    assert len({persona["detailed_attributes"]["ml_provenance"]["record_id"] for persona in personas}) == 2
    async with ml_api_app.app.state.db_sessionmaker() as session:
        active = list((await session.scalars(select(Personas).where(
            Personas.business_id == business_id, Personas.owner_id == "usr_test_fixture",
            Personas.status != "archived",
        ))).all())
        assert {persona.id for persona in active} == {persona["id"] for persona in personas}
    original = ml_api_app.get(f"/api/personas/{personas[0]['id']}", headers=ml_auth_headers)
    assert original.status_code == 200, original.text
    for field in ("name", "age", "occupation", "location", "description", "detailed_attributes"):
        assert original.json()[field] == personas[0][field]
    assert ml_api_app.app.state.ml_test_llm.calls == []


@pytest.mark.parametrize("attach_study", [True, False], ids=["study", "standalone"])
async def test_repeated_dataset_generation_appends_distinct_sources_and_updates_active_count(
    ml_api_app, ml_auth_headers, ml_uploaded_dataset, ml_study, attach_study,
) -> None:
    dataset_id = ml_uploaded_dataset["id"]
    study_id = ml_study if attach_study else None
    if not attach_study:
        async with ml_api_app.app.state.db_sessionmaker() as session:
            dataset = await session.get(DatasetSources, dataset_id)
            dataset.study_id = None
            await session.commit()
    source_batches = []
    for generation_number in range(2):
        response = ml_api_app.post(
            f"/api/datasets/{dataset_id}/generate-personas",
            json={"requested_count": 2, "study_id": study_id, "business_description": "Food delivery and study planning"},
            headers=ml_auth_headers,
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["generated_count"] == result["requested_count"] == 2
        assert result["failed_count"] == 0
        source_batches.append({
            persona["detailed_attributes"]["ml_provenance"]["record_id"]
            for persona in result["personas"]
        })
        assert len(source_batches[-1]) == 2
    assert source_batches[0].isdisjoint(source_batches[1])
    async with ml_api_app.app.state.db_sessionmaker() as session:
        active = list((await session.scalars(select(Personas).where(
            Personas.study_id == study_id, Personas.owner_id == "usr_test_fixture",
            Personas.status != "archived",
        ))).all())
        assert len(active) == 4
        assert (await session.get(DatasetSources, dataset_id)).persona_count_generated == 4
        if attach_study:
            assert (await session.get(Studies, ml_study)).persona_count == len(active)
    assert ml_api_app.app.state.ml_test_llm.calls == []


@pytest.mark.parametrize("generation_path", ["study", "job", "dataset", "standalone"])
async def test_repeated_generation_exhaustion_preserves_original_batch_and_error_contract(
    ml_api_app, ml_auth_headers, ml_study, generation_path, request,
) -> None:
    is_dataset = generation_path in {"dataset", "standalone"}
    study_id = None if generation_path == "standalone" else ml_study
    age_ranges = [[21, 24], [27, 27]]
    if is_dataset:
        dataset_id = request.getfixturevalue("ml_uploaded_dataset")["id"]
        endpoint = f"/api/datasets/{dataset_id}/generate-personas"
        payload = {"requested_count": 2, "study_id": study_id, "business_description": "Food delivery and study planning"}
        async with ml_api_app.app.state.db_sessionmaker() as session:
            dataset = await session.get(DatasetSources, dataset_id)
            dataset.study_id = study_id
            dataset.segments = [
                {**segment, "constraints": {"age_range": age_range}}
                for segment, age_range in zip(dataset.segments, age_ranges, strict=True)
            ]
            await session.commit()
    else:
        endpoint = f"/api/studies/{ml_study}/personas/generate"
        payload = {"target_count": 2, "distribution_strategy": "equal"}
        async with ml_api_app.app.state.db_sessionmaker() as session:
            segments = list((await session.scalars(select(MarketSegments).where(
                MarketSegments.study_id == ml_study,
            ).order_by(MarketSegments.created_at.desc()))).all())
            for segment, age_range in zip(segments, age_ranges, strict=True):
                segment.characteristics = {"demographics": {"age_range": age_range}}
            await session.commit()

    async def finish_jobs() -> None:
        await asyncio.gather(*tuple(ml_api_app.app.state.async_job_tasks))

    original = {}
    for generation_number in range(2):
        response = ml_api_app.post(
            f"{endpoint}/jobs" if generation_path == "job" else endpoint,
            json=payload, headers=ml_auth_headers,
        )
        if generation_path == "job":
            assert response.status_code == 202, response.text
            ml_api_app.portal.call(finish_jobs)
            response = ml_api_app.get(
                f"{endpoint}/jobs/{response.json()['job_id']}", headers=ml_auth_headers,
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == ("completed" if generation_number == 0 else "failed"), response.text
        else:
            expected_status = (200 if is_dataset else 201) if generation_number == 0 else 422
            assert response.status_code == expected_status, response.text
        if generation_number == 1:
            assert response.json()["error_code"] == "ml_persona_unsupported_context"
            if generation_path != "job":
                assert response.json()["request_id"]
            if is_dataset:
                assert response.json()["failed"]
        async with ml_api_app.app.state.db_sessionmaker() as session:
            active = list((await session.scalars(select(Personas).where(
                Personas.study_id == study_id, Personas.owner_id == "usr_test_fixture",
                Personas.status != "archived",
            ))).all())
            assert len(active) == 2
            stored = {persona.id: (persona.name, persona.detailed_attributes) for persona in active}
            if generation_number == 0:
                original = stored
            else:
                assert stored == original
            if study_id:
                assert (await session.get(Studies, study_id)).persona_count == 2
            if is_dataset:
                assert (await session.get(DatasetSources, dataset_id)).persona_count_generated == 2
                runs = list((await session.scalars(select(DatasetPersonaRuns).where(
                    DatasetPersonaRuns.dataset_id == dataset_id,
                ))).all())
                assert len(runs) == 1
            else:
                runs = list((await session.scalars(select(PersonaGenerationRuns).where(
                    PersonaGenerationRuns.study_id == study_id,
                ).order_by(PersonaGenerationRuns.created_at))).all())
                assert [run.status for run in runs] == ["completed", *(["failed"] if generation_number else [])]
                assert runs[-1].generated_count == (2 if generation_number == 0 else 0)
    assert ml_api_app.app.state.ml_test_llm.calls == []


@pytest.mark.parametrize("generation_path", ["legacy", "study", "dataset"])
@pytest.mark.parametrize("existing_source", ["record_id", "normalized_name", "other_owner", "other_scope", "archived"])
async def test_generation_exclusions_respect_owner_scope_archives_and_normalized_names(
    ml_api_app, ml_auth_headers, ml_study, ml_training_records, generation_path, existing_source, request,
) -> None:
    source = ml_training_records[0]
    owner_id = "usr_foreign_ml" if existing_source == "other_owner" else "usr_test_fixture"
    if generation_path == "legacy":
        business = ml_api_app.post(
            "/api/businesses", json={"name": "Meal Planner", "description": "Food delivery and study planning"},
            headers=ml_auth_headers,
        )
        assert business.status_code == 201, business.text
        business_id = business.json()["id"]
        scope = Personas.business_id == business_id
        stored_scope = {"business_id": business_id}
        if existing_source == "other_scope":
            other_business = ml_api_app.post(
                "/api/businesses", json={"name": "Another Planner"}, headers=ml_auth_headers,
            )
            assert other_business.status_code == 201, other_business.text
            stored_scope = {"business_id": other_business.json()["id"]}
        endpoint = f"/api/businesses/{business_id}/personas"
        payload = {"min_age": 21, "max_age": 21}
    else:
        scope = Personas.study_id == ml_study
        stored_scope = {"study_id": "std_other_ml_scope" if existing_source == "other_scope" else ml_study}
        if generation_path == "study":
            endpoint = f"/api/studies/{ml_study}/personas/generate"
            payload = {"target_count": 1}
        else:
            dataset_id = request.getfixturevalue("ml_uploaded_dataset")["id"]
            endpoint = f"/api/datasets/{dataset_id}/generate-personas"
            payload = {"requested_count": 1, "study_id": ml_study, "business_description": "Food delivery planning"}

    async with ml_api_app.app.state.db_sessionmaker() as session:
        if existing_source == "other_owner":
            session.add(Users(
                id=owner_id, email="foreign-ml@test.local", full_name="Foreign Synthetic Owner",
                auth_provider="email", is_active=True, is_verified=True,
            ))
        if existing_source == "other_scope" and generation_path != "legacy":
            session.add(Studies(id="std_other_ml_scope", user_id=owner_id, title="Another private study"))
        if generation_path == "study":
            segments = (await session.scalars(select(MarketSegments).where(MarketSegments.study_id == ml_study))).all()
            for segment in segments:
                segment.characteristics = {"demographics": {"age_range": [21, 21]}}
        elif generation_path == "dataset":
            dataset = await session.get(DatasetSources, dataset_id)
            dataset.segments = [{**segment, "constraints": {"age_range": [21, 21]}} for segment in dataset.segments]
        session.add(Personas(
            id="per_existing_source", **stored_scope, user_id=owner_id, owner_id=owner_id,
            name="  TEST   PERSON   0  " if existing_source == "normalized_name" else "Unrelated stored label",
            status="archived" if existing_source == "archived" else "ready",
            detailed_attributes={} if existing_source == "normalized_name" else {"ml_provenance": {"record_id": source.record_id}},
        ))
        if existing_source in {"record_id", "normalized_name"} and generation_path != "legacy":
            (await session.get(Studies, ml_study)).persona_count = 1
        await session.commit()

    response = ml_api_app.post(endpoint, json=payload, headers=ml_auth_headers)
    exhausted = existing_source in {"record_id", "normalized_name"}
    assert response.status_code == (422 if exhausted else (200 if generation_path == "dataset" else 201)), response.text
    if exhausted:
        assert response.json()["error_code"] == "ml_persona_unsupported_context"
        assert response.json()["request_id"]
    else:
        persona = response.json() if generation_path == "legacy" else response.json()["personas"][0]
        assert persona["name"] == source.name
        assert persona["detailed_attributes"]["ml_provenance"]["record_id"] == source.record_id
    async with ml_api_app.app.state.db_sessionmaker() as session:
        active = list((await session.scalars(select(Personas).where(
            scope, Personas.owner_id == "usr_test_fixture", Personas.status != "archived",
        ))).all())
        assert len(active) == 1
        assert (active[0].id == "per_existing_source") is exhausted
        if generation_path != "legacy":
            assert (await session.get(Studies, ml_study)).persona_count == len(active)
    assert ml_api_app.app.state.ml_test_llm.calls == []


async def test_business_route_persists_and_reloads_rich_synthetic_profile(
    ml_api_app, ml_auth_headers, ml_training_records,
) -> None:
    created = ml_api_app.post(
        "/api/businesses",
        json={"name": "Meal Planner", "description": "Food delivery for students"},
        headers=ml_auth_headers,
    )
    assert created.status_code == 201, created.text
    generated = ml_api_app.post(
        f"/api/businesses/{created.json()['id']}/personas",
        json={"hints": "Plan study schedules", "audience_segment": "Students in Dhaka"},
        headers=ml_auth_headers,
    )
    assert generated.status_code == 201, generated.text
    persona = generated.json()
    assert persona["generation_model"].startswith("bebshax-persona-ml/")
    assert persona["location"] == "Austin, Texas, USA"
    assert persona["personality"] is None
    assert persona["evidence"] == []
    assert all(attribute["provenance_class"] == "SYNTHETIC" and attribute["evidence_ids"] == [] for attribute in persona["attributes"])

    fetched = ml_api_app.get(f"/api/personas/{persona['id']}", headers=ml_auth_headers)
    assert fetched.status_code == 200, fetched.text
    for field in ("name", "description", "personality", "detailed_attributes", "warnings", "generation_model"):
        assert fetched.json()[field] == persona[field]
    reloaded = fetched.json()
    source = next(
        record for record in ml_training_records
        if record.record_id == reloaded["detailed_attributes"]["ml_provenance"]["record_id"]
    )
    assert reloaded["name"] == (source.name or f"Synthetic profile {source.record_id}")
    assert reloaded["age"] == source.age
    assert reloaded["occupation"] == source.occupation
    assert reloaded["location"] == source.location
    assert reloaded["education"] == (source.education or "Not available in training data")
    assert reloaded["description"] == source.description
    assert reloaded["income_range"] == "Not available in training data"
    assert reloaded["detailed_attributes"]["source_documents"] == source.documents
    assert reloaded["detailed_attributes"]["claim_provenance"] == {
        group: [{"value": value, "provenance": "SYNTHETIC", "evidence_ids": []} for value in values]
        for group, values in (
            ("goals", source.goals), ("pain_points", source.pain_points), ("behaviors", source.behaviors),
        )
    }
    assert all(attribute["confidence"] is None for attribute in reloaded["attributes"])
    async with ml_api_app.app.state.db_sessionmaker() as session:
        stored = await session.get(Personas, persona["id"])
        assert stored is not None
        assert stored.owner_id == "usr_test_fixture"
        assert stored.detailed_attributes == persona["detailed_attributes"]
        assert stored.bio == persona["description"]
        assert stored.validation_warnings == persona["warnings"]
        assert stored.dataset_refs == [persona["detailed_attributes"]["ml_provenance"]]
        assert stored.evidence_citations == []
        assert stored.goals == source.goals
        assert stored.pain_points == source.pain_points
        assert stored.behaviors == source.behaviors
    assert ml_api_app.app.state.ml_test_llm.calls == []


@pytest.mark.parametrize("generation_path", ["legacy", "study", "workflow", "dataset"])
def test_reloaded_ml_persona_keeps_identity_in_unchanged_interview(
    ml_api_app, ml_auth_headers, ml_study, ml_training_records, generation_path, request,
) -> None:
    if generation_path == "legacy":
        business = ml_api_app.post(
            "/api/businesses", json={"name": "Meal Planner", "description": "Food delivery and study planning"},
            headers=ml_auth_headers,
        )
        assert business.status_code == 201, business.text
        generated = ml_api_app.post(
            f"/api/businesses/{business.json()['id']}/personas", json={}, headers=ml_auth_headers,
        )
        assert generated.status_code == 201, generated.text
        persona = generated.json()
        persona_url = f"/api/personas/{persona['id']}"
    elif generation_path == "study":
        generated = ml_api_app.post(
            f"/api/studies/{ml_study}/personas/generate", json={"target_count": 1}, headers=ml_auth_headers,
        )
        assert generated.status_code == 201, generated.text
        persona = generated.json()["personas"][0]
        persona_url = f"/api/studies/{ml_study}/personas/{persona['id']}"
    elif generation_path == "workflow":
        payload = request.getfixturevalue("ml_workflow_payload")
        payload["roles"] = [{**payload["roles"][0], "count": 1}]
        generated = ml_api_app.post("/api/study/generate-personas", json=payload, headers=ml_auth_headers)
        assert generated.status_code == 200, generated.text
        persona = generated.json()["personas"][0]
        persona_url = f"/api/studies/{ml_study}/personas/{persona['id']}"
    else:
        dataset = request.getfixturevalue("ml_uploaded_dataset")
        generated = ml_api_app.post(
            f"/api/datasets/{dataset['id']}/generate-personas",
            json={"requested_count": 1, "study_id": ml_study, "business_description": "Food delivery and study planning"},
            headers=ml_auth_headers,
        )
        assert generated.status_code == 200, generated.text
        listed = ml_api_app.get(f"/api/studies/{ml_study}/personas", headers=ml_auth_headers)
        assert listed.status_code == 200, listed.text
        assert len(listed.json()["personas"]) == 1
        persona = listed.json()["personas"][0]
        persona_url = f"/api/studies/{ml_study}/personas/{persona['id']}"
    reloaded = ml_api_app.get(persona_url, headers=ml_auth_headers)
    assert reloaded.status_code == 200, reloaded.text
    before = reloaded.json()
    source = next(
        record for record in ml_training_records
        if record.record_id == before["detailed_attributes"]["ml_provenance"]["record_id"]
    )
    assert before["detailed_attributes"]["source_documents"] == source.documents
    assert ml_api_app.app.state.ml_test_llm.calls == []
    assert ml_api_app.app.state.persona_ml._model is not None

    started = ml_api_app.post(
        "/api/conversations", json={"persona_id": persona["id"], "objective": "Meal planning habits"},
        headers=ml_auth_headers,
    )
    assert started.status_code == 201, started.text
    conversation_id = started.json()["id"]
    replied = ml_api_app.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "How do you plan your work and meals?"}, headers=ml_auth_headers,
    )
    assert replied.status_code == 200, replied.text
    requests = ml_api_app.app.state.ml_test_llm.requests
    interview_requests = [request for request in requests if request.task == TaskType.PERSONA_INTERVIEW]
    assert len(interview_requests) == 1
    prompt = "\n".join(message.content for message in interview_requests[0].messages)
    for identity in (
        before["name"], str(source.age), source.occupation, source.location,
        source.education or "Not available in training data", source.description,
        *source.goals, *source.pain_points, *source.behaviors,
    ):
        assert identity in prompt
    assert "Big Five Traits:" not in prompt
    assert all(request.task not in {TaskType.PERSONA_GENERATION, TaskType.PERSONA_REFINEMENT} for request in requests)
    transcript = ml_api_app.get(f"/api/conversations/{conversation_id}", headers=ml_auth_headers)
    assert transcript.status_code == 200, transcript.text
    persona_turns = [turn for turn in transcript.json()["turns"] if turn["role"] == "persona"]
    assert len(persona_turns) == 1
    assert persona_turns[0]["content"] == "I use a calendar to plan work and meals."
    assert replied.json()["served_by"] == "pollinations/deepseek-r1"
    after = ml_api_app.get(persona_url, headers=ml_auth_headers)
    assert after.status_code == 200, after.text
    assert after.json() == before


def test_legacy_generation_preserves_business_fields_and_explicit_age(
    ml_api_app, ml_auth_headers, monkeypatch,
) -> None:
    business_fields = {
        "name": "Meal Planner", "description": "Food delivery description_tail",
        "industry": "Food planning category_tail", "target_market": "Dhaka market_tail",
    }
    created = ml_api_app.post("/api/businesses", json=business_fields, headers=ml_auth_headers)
    assert created.status_code == 201, created.text
    contexts = []
    original_generate = MLPersonaAdapter.generate

    async def capture(adapter, context, *args, **kwargs):
        contexts.append(context)
        return await original_generate(adapter, context, *args, **kwargs)

    monkeypatch.setattr(MLPersonaAdapter, "generate", capture)
    response = ml_api_app.post(
        f"/api/businesses/{created.json()['id']}/personas",
        json={
            "hints": "Food planning hints_tail", "generation_hints": ["Meal delivery generation_tail"],
            "audience_segment": "Dhaka students audience_tail", "min_age": 21, "max_age": 21,
        },
        headers=ml_auth_headers,
    )
    assert response.status_code == 201, response.text
    serialized = json.dumps(contexts[0].model_dump())
    for value in (*business_fields.values(), "hints_tail", "generation_tail", "audience_tail"):
        assert value in serialized
    assert contexts[0].min_age == contexts[0].max_age == 21
    assert response.json()["age"] == 21
    assert response.json()["location"] == "Austin, Texas, USA"
    assert ml_api_app.app.state.ml_test_llm.calls == []


@pytest.mark.parametrize("ml_api_app", ["ready", "missing", "corrupt"], indirect=True)
def test_existing_copilot_chat_stays_on_fake_llm_independent_of_ml_artifact(
    ml_api_app, ml_auth_headers,
) -> None:
    reply = "Which meal planning habit do you need to validate first?"
    adapter = ml_api_app.app.state.ml_test_llm
    for route in adapter._routes.values():
        route.reply = json.dumps({"reply": reply, "is_ready_for_approval": False, "suggested_roles": []})
    response = ml_api_app.post(
        "/api/study/copilot",
        json={"messages": [{"role": "user", "content": "Food delivery and study planning for students"}]},
        headers=ml_auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["reply"] == reply
    assert response.json()["served_by"] == "pollinations/deepseek-r1"
    assert response.json()["llm_request_id"]
    assert response.json()["fallback_reason"] is None
    assert [request.task for request in adapter.requests] == [TaskType.STRUCTURED_OUTPUT]
    assert ml_api_app.app.state.persona_ml._model is None


@pytest.mark.parametrize("ml_api_app", ["missing", "corrupt"], indirect=True)
def test_business_route_fails_explicitly_without_artifact(ml_api_app, ml_auth_headers) -> None:
    created = ml_api_app.post(
        "/api/businesses",
        json={"name": "Meal Planner", "description": "Food delivery for students"},
        headers=ml_auth_headers,
    )
    assert created.status_code == 201, created.text
    response = ml_api_app.post(
        f"/api/businesses/{created.json()['id']}/personas", json={}, headers=ml_auth_headers,
    )

    assert response.status_code == 503, response.text
    assert response.json()["error_code"] == "ml_persona_unavailable"
    assert response.json()["request_id"]
    assert "private-missing-artifact" not in response.text
    assert "metadata.json" not in response.text
    assert ml_api_app.app.state.ml_test_llm.calls == []


async def test_study_sync_and_regeneration_preserve_quota_shape_and_rich_fields(
    ml_api_app, ml_auth_headers, ml_study,
) -> None:
    response = ml_api_app.post(
        f"/api/studies/{ml_study}/personas/generate",
        json={"target_count": 5, "distribution_strategy": "population_weighted"},
        headers=ml_auth_headers,
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["run"]["status"] == "completed"
    assert result["run"]["generated_count"] == result["run"]["target_count"] == 5
    assert Counter(persona["segment_id"] for persona in result["personas"]) == {"seg_ml_young": 3, "seg_ml_older": 2}
    source_ids = {persona["detailed_attributes"]["ml_provenance"]["record_id"] for persona in result["personas"]}
    assert len(source_ids) == 5
    original = result["personas"][0]
    fetched = ml_api_app.get(
        f"/api/studies/{ml_study}/personas/{original['id']}", headers=ml_auth_headers,
    )
    assert fetched.status_code == 200, fetched.text
    for field, value in original.items():
        if field not in {"created_at", "updated_at"}:
            assert fetched.json()[field] == value
    regenerated = ml_api_app.post(
        f"/api/studies/{ml_study}/personas/{original['id']}/regenerate", headers=ml_auth_headers,
    )
    assert regenerated.status_code == 200, regenerated.text
    fresh = regenerated.json()
    assert fresh["id"] == original["id"]
    assert fresh["version"] == 2
    assert fresh["detailed_attributes"]["ml_provenance"]["record_id"] not in source_ids
    assert fresh["generation_model"].startswith("bebshax-persona-ml/")
    assert fresh["evidence_citations"] == []
    assert fresh["commercial_profile"] == {}
    assert fresh["personality"] == {}
    assert fresh["is_synthetic"] is True
    async with ml_api_app.app.state.db_sessionmaker() as session:
        row = await session.get(Personas, fresh["id"])
        assert row.owner_id == "usr_test_fixture"
        assert row.detailed_attributes == fresh["detailed_attributes"]
        assert row.dataset_refs == fresh["dataset_refs"]
    assert ml_api_app.app.state.ml_test_llm.calls == []


def test_study_generation_job_completes_with_local_artifact(ml_api_app, ml_auth_headers, ml_study) -> None:
    started = ml_api_app.post(
        f"/api/studies/{ml_study}/personas/generate/jobs",
        json={"personas_per_segment": 1, "distribution_strategy": "equal"},
        headers=ml_auth_headers,
    )
    assert started.status_code == 202, started.text

    async def finish_jobs() -> None:
        await asyncio.gather(*tuple(ml_api_app.app.state.async_job_tasks))

    ml_api_app.portal.call(finish_jobs)
    polled = ml_api_app.get(
        f"/api/studies/{ml_study}/personas/generate/jobs/{started.json()['job_id']}",
        headers=ml_auth_headers,
    )
    assert polled.status_code == 200, polled.text
    job = polled.json()
    assert job["status"] == "completed", job
    assert job["result"]["run"]["generated_count"] == 2
    assert len({persona["detailed_attributes"]["ml_provenance"]["record_id"] for persona in job["result"]["personas"]}) == 2
    assert ml_api_app.app.state.ml_test_llm.calls == []


@pytest.mark.parametrize("ml_api_app", ["missing", "corrupt"], indirect=True)
def test_study_generation_has_explicit_model_unavailable_envelope(ml_api_app, ml_auth_headers, ml_study) -> None:
    response = ml_api_app.post(
        f"/api/studies/{ml_study}/personas/generate", json={"target_count": 1}, headers=ml_auth_headers,
    )
    assert response.status_code == 503, response.text
    assert response.json()["error_code"] == "ml_persona_unavailable"
    assert ml_api_app.app.state.ml_test_llm.calls == []


@pytest.mark.parametrize("ml_api_app", ["missing"], indirect=True)
def test_persona_job_retains_model_error_code(ml_api_app, ml_auth_headers, ml_study) -> None:
    started = ml_api_app.post(
        f"/api/studies/{ml_study}/personas/generate/jobs", json={"target_count": 1}, headers=ml_auth_headers,
    )
    assert started.status_code == 202, started.text

    async def finish_jobs() -> None:
        await asyncio.gather(*tuple(ml_api_app.app.state.async_job_tasks))

    ml_api_app.portal.call(finish_jobs)
    polled = ml_api_app.get(
        f"/api/studies/{ml_study}/personas/generate/jobs/{started.json()['job_id']}", headers=ml_auth_headers,
    )
    assert polled.json()["status"] == "failed"
    assert polled.json()["error_code"] == "ml_persona_unavailable"
    assert "private-missing-artifact" not in polled.text
    assert ml_api_app.app.state.ml_test_llm.calls == []


@pytest.mark.parametrize("drop_ml_state", [False, True])
async def test_workflow_without_router_preserves_context_role_order_and_both_stores(
    ml_api_app, ml_auth_headers, ml_workflow_payload, monkeypatch, drop_ml_state,
) -> None:
    del ml_api_app.app.state.llm_router
    if drop_ml_state:
        del ml_api_app.app.state.persona_ml
    contexts = []
    original_generate = MLPersonaAdapter.generate

    async def capture(adapter, context, *args, **kwargs):
        contexts.append(context)
        return await original_generate(adapter, context, *args, **kwargs)

    monkeypatch.setattr(MLPersonaAdapter, "generate", capture)
    async with ml_api_app.app.state.db_sessionmaker() as session:
        study = await session.get(Studies, ml_workflow_payload["study_id"])
        study.prompt += " stored_business_tail"
        session.add(Personas(
            id="per_previous_ml", study_id=ml_workflow_payload["study_id"],
            owner_id="usr_test_fixture", user_id="usr_test_fixture", name="Previous synthetic profile", status="active",
        ))
        await session.commit()

    response = ml_api_app.post("/api/study/generate-personas", json=ml_workflow_payload, headers=ml_auth_headers)
    assert response.status_code == 200, response.text
    result = response.json()
    personas = result["personas"]
    assert result["failed_roles"] == []
    assert [persona["role_id"] for persona in personas] == ["role_first", "role_first", "role_second", "role_second"]
    assert len({persona["detailed_attributes"]["ml_provenance"]["record_id"] for persona in personas}) == 4
    assert result["served_by"] and all(model.startswith("bebshax-persona-ml/") for model in result["served_by"])
    serialized_context = json.dumps(contexts[0].model_dump())
    for text in ("context_tail", "stored_business_tail", "collected_context_tail", "research_tail", "role_description_tail", "demand_validation", "BDT 200 per month", "Students and workers in Dhaka", "research claim 6"):
        assert text in serialized_context
    for persona in personas:
        assert persona["demographics"]["location"] == "Austin, Texas, USA"
        assert persona["demographics"]["occupation"] not in {"Pilot", "Artist"}
        assert persona["grounding_ratio"] == 0.0
        assert persona["grounding_basis"] == "synthetic_training_proxy"
        assert persona["evidence_claim_count"] == 7
        assert persona["evidence_citations"] == []
        assert all(attribute["provenance_class"] == "SYNTHETIC" and attribute["evidence_ids"] == [] for attribute in persona["attributes"])

    async with ml_api_app.app.state.db_sessionmaker() as session:
        study = await session.get(Studies, ml_workflow_payload["study_id"])
        assert study.personas_data == personas
        assert study.persona_ids == [persona["id"] for persona in personas]
        assert study.persona_count == 4
        assert (await session.get(Personas, "per_previous_ml")).status == "archived"
        for persona in personas:
            stored = await session.get(Personas, persona["id"])
            assert stored.owner_id == "usr_test_fixture"
            assert stored.bio == persona["description"]
            assert stored.demographics == persona["demographics"]
            assert stored.behaviors == persona["behaviors"]
            assert stored.detailed_attributes == persona["detailed_attributes"]
            assert stored.validation_warnings == persona["validation_warnings"]
            assert stored.dataset_refs == persona["dataset_refs"]
            assert stored.evidence_citations == []
            assert stored.is_synthetic is True
    assert isinstance(ml_api_app.app.state.persona_ml, MLPersonaAdapter)
    assert ml_api_app.app.state.ml_test_llm.calls == []


@pytest.mark.parametrize("ml_api_app", ["missing", "corrupt"], indirect=True)
def test_workflow_unavailable_model_never_falls_back_to_llm(ml_api_app, ml_auth_headers, ml_workflow_payload) -> None:
    response = ml_api_app.post("/api/study/generate-personas", json=ml_workflow_payload, headers=ml_auth_headers)
    assert response.status_code == 503, response.text
    assert response.json()["error_code"] == "ml_persona_unavailable"
    assert "private-missing-artifact" not in response.text
    assert ml_api_app.app.state.ml_test_llm.calls == []


@pytest.mark.parametrize(("minimum", "maximum", "expected_status"), [(21, 24, 200), (90, 95, 422), (40, 20, 422)])
def test_workflow_enforces_explicit_role_age_constraints(
    ml_api_app, ml_auth_headers, ml_workflow_payload, minimum, maximum, expected_status,
) -> None:
    ml_workflow_payload["roles"] = [{
        **ml_workflow_payload["roles"][0], "min_age": minimum, "max_age": maximum,
    }]
    response = ml_api_app.post("/api/study/generate-personas", json=ml_workflow_payload, headers=ml_auth_headers)
    assert response.status_code == expected_status, response.text
    if expected_status == 200:
        personas = response.json()["personas"]
        assert len(personas) == 2
        assert all(minimum <= persona["age"] <= maximum for persona in personas)
        assert len({persona["detailed_attributes"]["ml_provenance"]["record_id"] for persona in personas}) == 2
    else:
        assert response.json()["error_code"] == "ml_persona_unsupported_context"
    assert ml_api_app.app.state.ml_test_llm.calls == []


@pytest.mark.parametrize("include_supported_role", [False, True])
def test_workflow_unsupported_role_preserves_partial_error_envelope(
    ml_api_app, ml_auth_headers, ml_workflow_payload, include_supported_role,
) -> None:
    # An impossible age band is a genuine model refusal (an oversize role title
    # is no longer one: overflow text is carried as research instead of refused).
    invalid_role = {"id": "impossible", "role": "Centenarian", "description": "Food planning", "count": 1, "selected": True, "min_age": 90, "max_age": 95}
    ml_workflow_payload["roles"] = [invalid_role, *ml_workflow_payload["roles"][:1]] if include_supported_role else [invalid_role]
    response = ml_api_app.post("/api/study/generate-personas", json=ml_workflow_payload, headers=ml_auth_headers)
    if include_supported_role:
        assert response.status_code == 200, response.text
        assert len(response.json()["personas"]) == 2
        assert [failed["role_id"] for failed in response.json()["failed_roles"]] == ["impossible"]
        assert response.json()["failed_roles"][0]["error_code"] == "ml_persona_unsupported_context"
        assert "Insufficient" in response.json()["failed_roles"][0]["detail"]
    else:
        assert response.status_code == 422, response.text
        assert response.json()["error_code"] == "ml_persona_unsupported_context"
    assert ml_api_app.app.state.ml_test_llm.calls == []


def test_workflow_oversize_role_title_is_carried_as_context_not_refused(ml_api_app, ml_auth_headers, ml_workflow_payload) -> None:
    ml_workflow_payload["roles"] = [{**ml_workflow_payload["roles"][0], "role": "Meal planner " * 60}]
    response = ml_api_app.post("/api/study/generate-personas", json=ml_workflow_payload, headers=ml_auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["failed_roles"] == []
    assert len(response.json()["personas"]) == 2


async def test_dataset_route_preserves_distribution_audit_and_rich_reload_without_router(
    ml_api_app, ml_auth_headers, ml_uploaded_dataset, ml_study,
) -> None:
    del ml_api_app.app.state.llm_router
    dataset_id = ml_uploaded_dataset["id"]
    response = ml_api_app.post(
        f"/api/datasets/{dataset_id}/generate-personas",
        json={"requested_count": 4, "study_id": ml_study, "business_name": "Meal Planner", "business_description": "Food delivery and study planning"},
        headers=ml_auth_headers,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["requested_count"] == result["generated_count"] == 4
    assert result["failed_count"] == 0 and result["failed"] == []
    assert sum(result["distribution"].values()) == 4
    actual_distribution = Counter(persona["segment_id"] for persona in result["personas"])
    assert all(actual_distribution[segment] == count for segment, count in result["distribution"].items())
    assert len({persona["detailed_attributes"]["ml_provenance"]["record_id"] for persona in result["personas"]}) == 4
    assert all(model.startswith("bebshax-persona-ml/") for model in result["served_by"])
    for persona in result["personas"]:
        assert persona["location"] == "Austin, Texas, USA"
        assert persona["income_range"] == "Not available in training data"
        assert persona["personality"] is None
        assert all(claim["provenance"] == "SYNTHETIC" and claim["evidence_ids"] == [] for claim in persona["goals"])
    async with ml_api_app.app.state.db_sessionmaker() as session:
        run = await session.get(DatasetPersonaRuns, result["run_id"])
        assert run.generated_count == 4
        assert run.distribution_target == run.distribution_actual == result["distribution"]
        dataset = await session.get(DatasetSources, dataset_id)
        assert dataset.persona_count_generated == 4
        rows = list((await session.execute(select(Personas).where(Personas.dataset_persona_run_id == result["run_id"]))).scalars())
        assert len(rows) == 4
        for row in rows:
            assert row.generation_run_id is None and row.segment_id is None
            assert row.dataset_version_id == result["dataset_version_id"]
            expected = next(persona for persona in result["personas"] if persona["detailed_attributes"]["ml_provenance"] == row.detailed_attributes["ml_provenance"])
            assert row.dataset_segment_key == expected["segment_id"]
            assert row.owner_id == "usr_test_fixture"
            assert row.bio == expected["description"]
            assert row.validation_warnings == expected["validation"]["warnings"]
            assert any("proxy" in warning for warning in row.validation_warnings)
            assert expected["detailed_attributes"]["ml_provenance"] in row.dataset_refs
            assert row.evidence_citations == []
            fetched = ml_api_app.get(f"/api/personas/{row.id}", headers=ml_auth_headers)
            assert fetched.status_code == 200, fetched.text
            assert fetched.json()["detailed_attributes"] == row.detailed_attributes
            assert fetched.json()["dataset_refs"] == row.dataset_refs
    assert ml_api_app.app.state.ml_test_llm.calls == []


@pytest.mark.parametrize("ml_api_app", ["missing", "corrupt"], indirect=True)
def test_dataset_route_preserves_model_unavailable_error_code(
    ml_api_app, ml_auth_headers, ml_uploaded_dataset, ml_study,
) -> None:
    response = ml_api_app.post(
        f"/api/datasets/{ml_uploaded_dataset['id']}/generate-personas",
        json={"requested_count": 2, "study_id": ml_study, "business_description": "Food delivery planning"},
        headers=ml_auth_headers,
    )
    assert response.status_code == 503, response.text
    assert response.json()["error_code"] == "ml_persona_unavailable"
    assert "private-missing-artifact" not in response.text
    assert ml_api_app.app.state.ml_test_llm.calls == []


async def test_dataset_route_rejects_unsupported_age_without_substitution(
    ml_api_app, ml_auth_headers, ml_uploaded_dataset, ml_study,
) -> None:
    async with ml_api_app.app.state.db_sessionmaker() as session:
        dataset = await session.get(DatasetSources, ml_uploaded_dataset["id"])
        dataset.segments = [{**segment, "constraints": {"age_range": [90, 95]}} for segment in dataset.segments]
        await session.commit()
    response = ml_api_app.post(
        f"/api/datasets/{ml_uploaded_dataset['id']}/generate-personas",
        json={"requested_count": 1, "study_id": ml_study, "business_description": "Food delivery planning"},
        headers=ml_auth_headers,
    )
    assert response.status_code == 422, response.text
    assert response.json()["error_code"] == "ml_persona_unsupported_context"
    assert ml_api_app.app.state.ml_test_llm.calls == []