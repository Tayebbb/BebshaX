from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, Request
from sqlalchemy import delete, event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.api.errors import APIError
from bebshax.api.jobs import get_job_async, shutdown_jobs
from bebshax.auth.models import Users
from bebshax.datasets import service as datasets
from bebshax.datasets.orm import DatasetVersions
from bebshax.db.models import Base, DatasetPersonaRuns, DatasetSources, Personas, Studies
from bebshax.jobs.orm import JobCheckpoints
from bebshax.jobs.store import SQLJobStore
from bebshax.personas.ml_adapter import MLPersonaAdapter
from bebshax.personas.orm import PersonaSourceSelections, PersonaVersions
from bebshax.personas.service import record_persona_version, refresh_study_persona_state, serialize_persona


@pytest.fixture
async def dataset_persona_context(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    monkeypatch.setattr(datasets, "_upload_dir", lambda: upload_root)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'persona-lifecycle.sqlite'}")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    segment = {
        "id": "local-segment", "name": "Synthetic participants", "count": 2,
        "population_share": 1.0, "population_percentage": 100.0,
        "constraints": {}, "sample_records": [{"age": 25}, {"age": 30}],
    }
    records = json.dumps(segment["sample_records"]).encode("utf-8")
    digest = hashlib.sha256(records).hexdigest()
    file_path = upload_root / f"dataset-1.v_0123456789abcdef.{digest}.json"
    file_path.write_bytes(records)
    async with maker() as session, session.begin():
        session.add(Users(
            id="owner-1", email="dataset-owner@example.test", full_name="Synthetic owner",
            is_active=True, is_verified=True,
        ))
        await session.flush()
        session.add(Studies(id="study-1", user_id="owner-1", title="Synthetic study"))
        await session.flush()
        session.add(DatasetSources(
            id="dataset-1", user_id="owner-1", study_id="study-1", name="Synthetic dataset",
            source_type="upload", file_type="csv", file_path=str(file_path), content_hash=digest,
            status="ready", row_count=2, column_count=1, schema_metadata={}, statistics={},
            segments=[segment], persona_count_generated=0,
        ))
        await session.flush()
        session.add(DatasetVersions(
            id="version-1", dataset_id="dataset-1", owner_id="owner-1", version=1,
            content_hash=digest, records_hash=digest, file_path=str(file_path), file_type="csv",
            row_count=2, column_count=1, schema_metadata={}, statistics={}, segments=[segment],
        ))

    service = datasets.DatasetService(maker, ml_generator=Mock(spec=MLPersonaAdapter))

    async def generated_segment(
        dataset, selected_segment, count, business_name, business_description,
        study_context, claims, exclude_ids, exclude_names,
    ):
        available = [index for index in range(20) if f"record-{index}" not in exclude_ids]
        return [{
            "name": f"Synthetic participant {index}", "age": 25, "occupation": "Research participant",
            "description": "Synthetic profile for persistence tests.", "segment_id": selected_segment["id"],
            "segment_name": selected_segment["name"], "served_by": "persona-ml/fixture-model",
            "model_used": "persona-ml/fixture-model", "goals": [], "pain_points": [],
            "needs": [], "motivations": [], "behaviors": [],
            "validation": {"status": "VALID", "violations": [], "warnings": []},
            "detailed_attributes": {"ml_provenance": {
                "record_id": f"record-{index}", "source": "synthetic-fixture", "model_version": "fixture-model",
            }},
        } for index in available[:count]]

    monkeypatch.setattr(service, "_generate_ml_segment", generated_segment)
    try:
        yield SimpleNamespace(service=service, maker=maker, file_path=file_path)
    finally:
        await engine.dispose()


@pytest.mark.parametrize("study_id", ["study-1", None], ids=["study", "standalone"])
async def test_dataset_cohort_has_immutable_versions_and_canonical_study_projection(dataset_persona_context, study_id):
    context = dataset_persona_context
    async with context.maker() as session, session.begin():
        dataset = await session.get(DatasetSources, "dataset-1")
        dataset.study_id = study_id
    original_snapshots = {}
    selected_sources = set()
    for generation in range(2):
        result = await context.service.generate_personas_from_dataset(
            "dataset-1", requested_count=2, user_id="owner-1", study_id=study_id,
        )
        assert result["generated_count"] == 2
        assert result["failed_count"] == 0
        async with context.maker() as session:
            personas = list((await session.scalars(select(Personas).order_by(Personas.created_at, Personas.id))).all())
            snapshots = list((await session.scalars(select(PersonaVersions))).all())
            assert len(snapshots) == len(personas) == 2 * (generation + 1)
            selections = list((await session.scalars(select(PersonaSourceSelections))).all())
            assert len(selections) == len(personas)
            assert all(selection.dataset_id == "dataset-1" and selection.persona_version == 1 for selection in selections)
            assert {selection.persona_id for selection in selections} == {persona.id for persona in personas}
            stored_snapshots = {snapshot.persona_id: snapshot.snapshot for snapshot in snapshots}
            assert {key: stored_snapshots[key] for key in original_snapshots} == original_snapshots
            for persona in personas:
                snapshot = stored_snapshots[persona.id]
                assert snapshot["name"] == persona.name
                assert snapshot["detailed_attributes"] == persona.detailed_attributes
                assert snapshot["dataset_persona_run_id"] == persona.dataset_persona_run_id
                assert persona.dataset_version_id == snapshot["dataset_version_id"] == "version-1"
                assert persona.dataset_segment_key == snapshot["dataset_segment_key"] == "local-segment"
                assert persona.generation_run_id is None and persona.segment_id is None
                run = await session.get(DatasetPersonaRuns, persona.dataset_persona_run_id)
                assert run.dataset_id == "dataset-1" and run.user_id == "owner-1"
                assert run.study_id == study_id
            dataset = await session.get(DatasetSources, "dataset-1")
            assert dataset.persona_count_generated == len(personas)
            study = await session.get(Studies, "study-1")
            if study_id:
                assert study.persona_count == len(personas)
                assert study.persona_ids == [persona.id for persona in personas]
                assert study.personas_data == [serialize_persona(persona) for persona in personas]
            else:
                assert study.persona_count == 0
                assert not study.persona_ids and not study.personas_data
            original_snapshots = deepcopy(stored_snapshots)
        sources = {persona["detailed_attributes"]["ml_provenance"]["record_id"] for persona in result["personas"]}
        assert not selected_sources.intersection(sources)
        selected_sources.update(sources)


async def test_dataset_selection_does_not_hold_a_database_transaction(dataset_persona_context, monkeypatch):
    context = dataset_persona_context
    active_sessions = set()
    original_generate = context.service._generate_ml_segment

    def begun(session, transaction, connection):
        active_sessions.add(session)

    def ended(session, transaction):
        if transaction.parent is None:
            active_sessions.discard(session)

    async def generate(*args, **kwargs):
        assert not active_sessions, "Dataset inference must not hold database transactions"
        return await original_generate(*args, **kwargs)

    monkeypatch.setattr(context.service, "_generate_ml_segment", generate)
    sync_class = context.maker.class_.sync_session_class
    event.listen(sync_class, "after_begin", begun)
    event.listen(sync_class, "after_transaction_end", ended)
    try:
        result = await context.service.generate_personas_from_dataset(
            "dataset-1", requested_count=2, user_id="owner-1", study_id="study-1",
        )
    finally:
        event.remove(sync_class, "after_begin", begun)
        event.remove(sync_class, "after_transaction_end", ended)
    assert result["generated_count"] == 2


@pytest.mark.parametrize("stage", ["snapshot", "projection"])
async def test_dataset_cohort_rolls_back_every_artifact_on_lifecycle_failure(dataset_persona_context, monkeypatch, stage):
    context = dataset_persona_context
    helper_name = "record_persona_version" if stage == "snapshot" else "refresh_study_persona_state"
    original_helper = getattr(datasets, helper_name)

    async def fail_after_write(*args, **kwargs):
        await original_helper(*args, **kwargs)
        raise RuntimeError("Synthetic lifecycle persistence failure")

    monkeypatch.setattr(datasets, helper_name, fail_after_write)
    with pytest.raises(RuntimeError, match="Synthetic lifecycle persistence failure"):
        await context.service.generate_personas_from_dataset(
            "dataset-1", requested_count=2, user_id="owner-1", study_id="study-1",
        )
    async with context.maker() as session:
        for model in (Personas, PersonaVersions, PersonaSourceSelections, DatasetPersonaRuns):
            assert (await session.scalars(select(model))).all() == []
        assert (await session.get(DatasetSources, "dataset-1")).persona_count_generated == 0
        study = await session.get(Studies, "study-1")
        assert study.persona_count == 0 and not study.persona_ids and not study.personas_data
    assert context.file_path.exists()


@pytest.mark.parametrize("target", ["dataset", "study"])
async def test_changed_input_during_dataset_selection_rejects_all_writes(dataset_persona_context, monkeypatch, target):
    context = dataset_persona_context
    original_generate = context.service._generate_ml_segment

    async def generate(*args, **kwargs):
        personas = await original_generate(*args, **kwargs)
        async with context.maker() as session, session.begin():
            if target == "dataset":
                dataset = await session.get(DatasetSources, "dataset-1")
                dataset.name = "Changed during selection"
            else:
                study = await session.get(Studies, "study-1")
                study.prompt = "Changed during selection"
        return personas

    monkeypatch.setattr(context.service, "_generate_ml_segment", generate)
    with pytest.raises(APIError) as raised:
        await context.service.generate_personas_from_dataset(
            "dataset-1", requested_count=2, user_id="owner-1", study_id="study-1",
        )
    assert raised.value.status_code == 409 and raised.value.error_code == "dataset_input_changed"
    async with context.maker() as session:
        for model in (Personas, PersonaVersions, PersonaSourceSelections, DatasetPersonaRuns):
            assert (await session.scalars(select(model))).all() == []
        assert (await session.get(DatasetSources, "dataset-1")).persona_count_generated == 0


async def test_competing_source_selection_is_rechecked_before_dataset_commit(dataset_persona_context, monkeypatch):
    context = dataset_persona_context
    original_generate = context.service._generate_ml_segment

    async def generate(*args, **kwargs):
        personas = await original_generate(*args, **kwargs)
        async with context.maker() as session, session.begin():
            competing = Personas(
                id="competing-persona", owner_id="owner-1", user_id="owner-1", study_id="study-1",
                name=personas[0]["name"], detailed_attributes=deepcopy(personas[0]["detailed_attributes"]),
                status="ready", version=1,
            )
            session.add(competing)
            await record_persona_version(session, competing)
            study = await session.get(Studies, "study-1")
            await refresh_study_persona_state(session, study=study, owner_id="owner-1", removed_ids=set())
        return personas

    monkeypatch.setattr(context.service, "_generate_ml_segment", generate)
    with pytest.raises(APIError) as raised:
        await context.service.generate_personas_from_dataset(
            "dataset-1", requested_count=2, user_id="owner-1", study_id="study-1",
        )
    assert raised.value.status_code == 409 and raised.value.error_code == "persona_source_conflict"
    async with context.maker() as session:
        assert (await session.scalars(select(Personas.id))).all() == ["competing-persona"]
        assert (await session.scalars(select(PersonaVersions.persona_id))).all() == ["competing-persona"]
        assert (await session.scalars(select(DatasetPersonaRuns))).all() == []
        assert (await session.get(DatasetSources, "dataset-1")).persona_count_generated == 0
        study = await session.get(Studies, "study-1")
        assert study.persona_count == 1 and study.persona_ids == ["competing-persona"]


async def test_legacy_dataset_origin_remains_readable_and_excluded_without_invented_history(dataset_persona_context):
    context = dataset_persona_context
    async with context.maker() as session, session.begin():
        dataset = await session.get(DatasetSources, "dataset-1")
        dataset.study_id = None
        dataset.persona_count_generated = 1
        session.add(DatasetPersonaRuns(
            id="legacy-run", dataset_id="dataset-1", user_id="owner-1", requested_count=1, generated_count=1,
            model_used="historical-model",
        ))
        await session.flush()
        session.add(Personas(
            id="legacy-persona", owner_id="owner-1", user_id="owner-1", name="Historical source",
            generation_run_id="legacy-run", segment_id="legacy-local-key", status="ready", version=3,
            detailed_attributes={"ml_provenance": {"source": "synthetic-fixture", "record_id": "record-0"}},
        ))
    result = await context.service.generate_personas_from_dataset("dataset-1", requested_count=2, user_id="owner-1")
    assert all(persona["detailed_attributes"]["ml_provenance"]["record_id"] != "record-0" for persona in result["personas"])
    async with context.maker() as session:
        legacy = await session.get(Personas, "legacy-persona")
        assert legacy.generation_run_id == "legacy-run" and legacy.segment_id == "legacy-local-key"
        assert legacy.dataset_persona_run_id is None and legacy.dataset_version_id is None and legacy.dataset_segment_key is None
        assert await session.get(PersonaVersions, (legacy.id, legacy.version)) is None
        assert (await session.get(DatasetSources, "dataset-1")).persona_count_generated == 3


async def test_dataset_generation_pins_the_published_pointer_not_highest_version(dataset_persona_context):
    context = dataset_persona_context
    async with context.maker() as session, session.begin():
        original = await session.get(DatasetVersions, "version-1")
        session.add(DatasetVersions(
            id="unpublished-version", dataset_id="dataset-1", owner_id="owner-1", version=2,
            content_hash="b" * 64, records_hash="b" * 64, file_path=str(context.file_path.with_name("unpublished.json")),
            file_type="csv", row_count=2, column_count=1, schema_metadata={}, statistics={}, segments=deepcopy(original.segments),
        ))
    result = await context.service.generate_personas_from_dataset(
        "dataset-1", requested_count=1, user_id="owner-1", study_id="study-1",
    )
    assert result["dataset_version_id"] == "version-1"
    assert result["personas"][0]["dataset_version_id"] == "version-1"


async def test_unversioned_dataset_refuses_new_inference_without_inventing_lineage(dataset_persona_context, monkeypatch):
    context = dataset_persona_context
    async with context.maker() as session, session.begin():
        await session.execute(delete(DatasetVersions))

    async def unexpected_inference(*args, **kwargs):
        pytest.fail("An unversioned dataset must not start inference")

    monkeypatch.setattr(context.service, "_generate_ml_segment", unexpected_inference)
    with pytest.raises(APIError) as raised:
        await context.service.generate_personas_from_dataset(
            "dataset-1", requested_count=1, user_id="owner-1", study_id="study-1",
        )
    assert raised.value.status_code == 409 and raised.value.error_code == "dataset_version_required"
    assert context.file_path.exists()


async def test_dataset_job_checkpoint_and_result_pin_the_same_version(dataset_persona_context, monkeypatch):
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", "synthetic-dataset-lifecycle-signing-value-0123456789")
    from bebshax.api.datasets import _dataset_command

    context = dataset_persona_context
    app = FastAPI()
    app.state.db_sessionmaker = context.maker
    app.state.job_store = SQLJobStore(context.maker)
    request = Request({
        "type": "http", "app": app, "method": "POST", "path": "/api/datasets/dataset-1/generate-personas",
        "headers": [(b"idempotency-key", b"dataset-version-cohort")], "query_string": b"",
    })

    async def operation(job):
        return await context.service.generate_personas_from_dataset(
            "dataset-1", requested_count=1, user_id="owner-1", study_id="study-1", job=job,
        )

    try:
        result = await _dataset_command(
            request, kind="dataset_personas", scope_id="dataset-1", user_id="owner-1",
            input_data={"dataset_id": "dataset-1", "study_id": "study-1", "requested_count": 1}, operation=operation,
        )
        repeated = await _dataset_command(
            request, kind="dataset_personas", scope_id="dataset-1", user_id="owner-1",
            input_data={"dataset_id": "dataset-1", "study_id": "study-1", "requested_count": 1}, operation=operation,
        )
        assert repeated == result
        recovered_app = FastAPI()
        recovered_app.state.db_sessionmaker = context.maker
        recovered_app.state.job_store = SQLJobStore(context.maker)
        try:
            recovered = await get_job_async(
                recovered_app, result["job_id"], kind="dataset_personas", scope_id="dataset-1", user_id="owner-1",
            )
            assert recovered["state"] == "completed"
            assert recovered["result_refs"]["version_id"] == result["dataset_version_id"] == "version-1"
            async with context.maker() as session:
                checkpoint = await session.get(JobCheckpoints, (result["job_id"], "dataset"))
                assert checkpoint.result_refs == recovered["result_refs"]
                assert (await session.scalars(select(Personas))).one().id == result["personas"][0]["id"]
        finally:
            await shutdown_jobs(recovered_app)
    finally:
        await shutdown_jobs(app)


async def test_dataset_http_admission_captures_version_and_rejects_a_changed_queued_input(dataset_persona_context, monkeypatch):
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", "synthetic-dataset-lifecycle-signing-value-0123456789")
    from bebshax.api import datasets as dataset_api

    context = dataset_persona_context
    app = FastAPI()
    app.state.db_sessionmaker = context.maker
    app.state.job_store = SQLJobStore(context.maker)
    request = Request({
        "type": "http", "app": app, "method": "POST", "path": "/api/datasets/dataset-1/generate-personas",
        "headers": [(b"idempotency-key", b"dataset-api-version")], "query_string": b"",
    })
    monkeypatch.setattr(dataset_api.limiter, "enabled", False)
    original_command = dataset_api._dataset_command

    async def changed_before_execution(request, **kwargs):
        assert kwargs["input_data"]["dataset_version_id"] == "version-1"
        async with context.maker() as session, session.begin():
            original = await session.get(DatasetVersions, "version-1")
            dataset = await session.get(DatasetSources, "dataset-1")
            dataset.file_path = str(context.file_path.with_name("new-published.json"))
            dataset.content_hash = "b" * 64
            session.add(DatasetVersions(
                id="version-2", dataset_id="dataset-1", owner_id="owner-1", version=2,
                content_hash=dataset.content_hash, records_hash="b" * 64, file_path=dataset.file_path,
                file_type="csv", row_count=2, column_count=1, schema_metadata={}, statistics={}, segments=deepcopy(original.segments),
            ))
        return await original_command(request, **kwargs)

    async def unexpected_inference(*args, **kwargs):
        pytest.fail("A changed admitted version must fail before inference")

    monkeypatch.setattr(dataset_api, "_dataset_command", changed_before_execution)
    monkeypatch.setattr(context.service, "_generate_ml_segment", unexpected_inference)
    async with context.maker() as session:
        owner = await session.get(Users, "owner-1")
    try:
        with pytest.raises(APIError) as raised:
            await dataset_api.generate_personas_from_dataset(
                "dataset-1", dataset_api.GeneratePersonasRequest(requested_count=1, study_id="study-1"),
                request, current_user=owner, service=context.service,
            )
        assert raised.value.status_code == 409 and raised.value.error_code == "dataset_input_changed"
        async with context.maker() as session:
            assert (await session.scalars(select(Personas))).all() == []
    finally:
        await shutdown_jobs(app)