"""Scoped persona lifecycle regressions with SQLite foreign keys enabled."""

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from inspect import unwrap
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from bebshax.api import copilot as copilot_module
from bebshax.api.errors import APIError
from bebshax.auth.models import Users
from bebshax.datasets import service as dataset_module
from bebshax.datasets.service import DatasetService
from bebshax.db.models import (
    Base, Businesses, DatasetPersonaRuns, DatasetSources, MarketSegments, PersonaGenerationRuns, Personas,
    SegmentationRuns, Studies,
)
from bebshax.interview.orm import Conversations, ConversationTurns, InterviewInsights
from bebshax.memory.orm import MemoryItems
from bebshax.persona.orm import PersonaAttributes, PersonaDetails, PersonaEvidence
from bebshax.personas import service as service_module
from bebshax.personas.generator import GeneratedPersonaDraft
from bebshax.personas.service import PersonaGenerationService


@pytest.fixture
async def exhibition_persona_db() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    def enable_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    event.listen(engine.sync_engine, "connect", enable_foreign_keys)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            assert await session.scalar(text("PRAGMA foreign_keys")) == 1
            session.add(Users(
                id="usr_lifecycle", email="lifecycle@example.test", full_name="Synthetic Owner",
                auth_provider="email", is_active=True, is_verified=True,
            ))
            await session.flush()
            session.add(Studies(
                id="std_lifecycle", user_id="usr_lifecycle", title="Lifecycle", step=2,
            ))
            await session.flush()
            latest = datetime(2026, 9, 9, tzinfo=timezone.utc)
            for run_id, created_at in (
                ("srun_old", latest - timedelta(days=1)), ("srun_new", latest),
            ):
                session.add(SegmentationRuns(
                    id=run_id, study_id="std_lifecycle", user_id="usr_lifecycle",
                    status="completed", created_at=created_at,
                ))
            await session.flush()
            for segment_id, run_id, created_at in (
                ("seg_old", "srun_old", latest - timedelta(days=1)),
                ("seg_new_1", "srun_new", latest),
                ("seg_new_2", "srun_new", latest + timedelta(minutes=1)),
            ):
                session.add(MarketSegments(
                    id=segment_id, study_id="std_lifecycle", user_id="usr_lifecycle",
                    segmentation_run_id=run_id, name=segment_id, description="Synthetic segment",
                    population_count=10, population_percentage=50.0, created_at=created_at,
                ))
            await session.commit()
        yield maker
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    ("selected_run_id", "expected_run_id", "expected_segments"),
    [
        (None, "srun_new", ["seg_new_2", "seg_new_1"]),
        ("srun_old", "srun_old", ["seg_old"]),
    ],
)
async def test_generation_uses_only_selected_segmentation_run(
    exhibition_persona_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch,
    selected_run_id: str | None, expected_run_id: str, expected_segments: list[str],
) -> None:
    observed: dict[str, Any] = {}

    class SelectionObserved(RuntimeError):
        pass

    async def observe_generation(**kwargs: Any) -> None:
        observed["segments"] = [segment.id for segment in kwargs["segments"]]
        observed["target_count"] = kwargs["target_count"]
        raise SelectionObserved

    monkeypatch.setattr(service_module, "generate_personas_for_study", observe_generation)
    async with exhibition_persona_db() as session:
        service = PersonaGenerationService(
            session, ml_generator=Mock(spec=service_module.MLPersonaAdapter),
        )
        with pytest.raises(SelectionObserved):
            await service.create_generation_run(
                "std_lifecycle", user_id="usr_lifecycle", segmentation_run_id=selected_run_id,
                personas_per_segment=2,
            )
        run = (await session.execute(select(PersonaGenerationRuns))).scalar_one()
        assert run.segmentation_run_id == expected_run_id
        assert observed["segments"] == expected_segments
        assert observed["target_count"] == len(expected_segments) * 2


@pytest.fixture
async def exhibition_run_artifacts(
    exhibition_persona_db: async_sessionmaker[AsyncSession],
) -> async_sessionmaker[AsyncSession]:
    async with exhibition_persona_db() as session:
        session.add(Users(
            id="usr_other_lifecycle", email="other-lifecycle@example.test",
            full_name="Other Synthetic Owner", auth_provider="email",
        ))
        await session.flush()
        session.add(Studies(
            id="std_other_lifecycle", user_id="usr_lifecycle", title="Other context",
        ))
        session.add_all([
            PersonaGenerationRuns(
                id=run_id, study_id="std_lifecycle", user_id="usr_lifecycle", status="completed",
            )
            for run_id in ("pgen_delete", "pgen_keep")
        ])
        await session.flush()
        for persona_id, study_id, owner_id, run_id in (
            ("per_delete", "std_lifecycle", "usr_lifecycle", "pgen_delete"),
            ("per_keep", "std_lifecycle", "usr_lifecycle", "pgen_keep"),
            ("per_foreign", "std_lifecycle", "usr_other_lifecycle", "pgen_delete"),
            ("per_other_context", "std_other_lifecycle", "usr_lifecycle", "pgen_delete"),
        ):
            session.add(Personas(
                id=persona_id, study_id=study_id, user_id=owner_id, owner_id=owner_id,
                generation_run_id=run_id, name=persona_id, status="ready",
            ))
            await session.flush()
            session.add_all([
                PersonaDetails(
                    persona_id=persona_id, age=30, occupation="Synthetic role", location="Test City",
                    income_range="Unknown", education="Unknown", description="Synthetic profile",
                ),
                PersonaAttributes(
                    id=f"attr_{persona_id}", persona_id=persona_id, key="goals", value="Plan meals",
                    provenance_class="SYNTHETIC",
                ),
                PersonaEvidence(
                    id=f"evidence_{persona_id}", persona_id=persona_id,
                    source="synthetic-fixture", text="Synthetic evidence",
                ),
                MemoryItems(
                    id=f"memory_{persona_id}", persona_id=persona_id, kind="episodic",
                    text="Synthetic memory", embedding=[0.0] * 384, embedding_space="test-384",
                    conversation_id=f"conversation_{persona_id}",
                ),
                Conversations(
                    id=f"conversation_{persona_id}", persona_id=persona_id,
                    study_id=study_id, user_id=owner_id, objective="Synthetic interview",
                ),
            ])
            await session.flush()
            session.add_all([
                ConversationTurns(
                    id=f"turn_{persona_id}", conversation_id=f"conversation_{persona_id}",
                    turn_number=1, role="persona", content="Synthetic response",
                ),
                InterviewInsights(
                    id=f"insight_{persona_id}", interview_id=f"conversation_{persona_id}",
                    study_id=study_id, user_id=owner_id, persona_id=persona_id,
                    type="need", title="Planning", description="Synthetic insight",
                ),
            ])
            await session.flush()
        study = await session.get(Studies, "std_lifecycle")
        assert study is not None
        study.persona_count = 2
        study.persona_ids = ["per_delete", "per_keep"]
        study.personas_data = [{"id": "per_delete"}, {"id": "per_keep"}]
        await session.commit()
    return exhibition_persona_db


async def test_delete_run_removes_owned_dependents_and_repairs_study_counts(
    exhibition_run_artifacts: async_sessionmaker[AsyncSession],
) -> None:
    async with exhibition_run_artifacts() as session:
        service = PersonaGenerationService(session)
        assert await service.delete_run("std_lifecycle", "pgen_delete", "usr_lifecycle")
    async with exhibition_run_artifacts() as session:
        assert await session.get(PersonaGenerationRuns, "pgen_delete") is None
        remaining = {"per_keep", "per_foreign", "per_other_context"}
        assert set((await session.scalars(select(Personas.id))).all()) == remaining
        for model in (PersonaDetails, PersonaAttributes, PersonaEvidence, MemoryItems, Conversations, InterviewInsights):
            assert set((await session.scalars(select(model.persona_id))).all()) == remaining
        assert set((await session.scalars(select(ConversationTurns.conversation_id))).all()) == {
            f"conversation_{persona_id}" for persona_id in remaining
        }
        study = await session.get(Studies, "std_lifecycle")
        assert study is not None
        assert study.persona_count == 1
        assert study.persona_ids == ["per_keep"]
        assert study.personas_data == [{"id": "per_keep"}]


async def test_delete_run_wrong_owner_changes_nothing(
    exhibition_run_artifacts: async_sessionmaker[AsyncSession],
) -> None:
    async with exhibition_run_artifacts() as session:
        assert not await PersonaGenerationService(session).delete_run(
            "std_lifecycle", "pgen_delete", "usr_other_lifecycle",
        )
        assert await session.get(Personas, "per_delete") is not None
        assert await session.get(MemoryItems, "memory_per_delete") is not None


async def test_delete_run_rolls_back_all_artifacts_when_commit_fails(
    exhibition_run_artifacts: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with exhibition_run_artifacts() as session:
        monkeypatch.setattr(session, "commit", AsyncMock(side_effect=RuntimeError("commit rejected")))
        with pytest.raises(RuntimeError, match="commit rejected"):
            await PersonaGenerationService(session).delete_run(
                "std_lifecycle", "pgen_delete", "usr_lifecycle",
            )
        assert not session.in_transaction()
    async with exhibition_run_artifacts() as session:
        assert await session.get(PersonaGenerationRuns, "pgen_delete") is not None
        assert await session.get(Personas, "per_delete") is not None
        assert await session.get(MemoryItems, "memory_per_delete") is not None
        assert await session.get(ConversationTurns, "turn_per_delete") is not None


async def test_delete_run_refuses_foreign_tenant_conversation_references(
    exhibition_run_artifacts: async_sessionmaker[AsyncSession],
) -> None:
    async with exhibition_run_artifacts() as session:
        conversation = await session.get(Conversations, "conversation_per_delete")
        assert conversation is not None
        conversation.user_id = "usr_other_lifecycle"
        await session.commit()
        with pytest.raises(APIError) as raised:
            await PersonaGenerationService(session).delete_run("std_lifecycle", "pgen_delete", "usr_lifecycle")
        assert raised.value.status_code == 409
        assert raised.value.error_code == "data_integrity"
    async with exhibition_run_artifacts() as session:
        assert await session.get(PersonaGenerationRuns, "pgen_delete") is not None
        assert await session.get(Conversations, "conversation_per_delete") is not None
        assert await session.get(MemoryItems, "memory_per_delete") is not None


async def test_active_source_exclusions_ignore_archived_foreign_and_other_context_personas(
    exhibition_run_artifacts: async_sessionmaker[AsyncSession],
) -> None:
    async with exhibition_run_artifacts() as session:
        for persona_id in ("per_delete", "per_keep", "per_foreign", "per_other_context"):
            persona = await session.get(Personas, persona_id)
            assert persona is not None
            persona.detailed_attributes = {"ml_provenance": {"record_id": f"source_{persona_id}"}}
            if persona_id == "per_keep":
                persona.status = "archived"
        await session.commit()
        await service_module.lock_persona_parent(session, owner_id="usr_lifecycle", study_id="std_lifecycle")
        exclude_ids, exclude_names = await service_module.active_source_exclusions(
            session, owner_id="usr_lifecycle", scope=Personas.study_id == "std_lifecycle",
        )
        assert exclude_ids == {"source_per_delete"}
        assert exclude_names == {"per_delete"}


@pytest.mark.parametrize(
    ("parent_type", "scope_key", "parent_id"),
    [(Studies, "study_id", "std_lifecycle"), (Businesses, "business_id", "biz_lifecycle"),
     (DatasetSources, "dataset_id", "ds_lifecycle")],
)
async def test_parent_lock_is_owner_scoped_and_does_not_commit(
    parent_type: type[Studies] | type[Businesses] | type[DatasetSources],
    scope_key: str, parent_id: str,
) -> None:
    parent = parent_type(id=parent_id)
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=parent))
    locked = await service_module.lock_persona_parent(
        session, owner_id="usr_lifecycle", **{scope_key: parent_id},
    )
    assert locked is parent
    statement = session.execute.call_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "FOR UPDATE" in str(compiled)
    assert parent_id in compiled.params.values()
    assert "usr_lifecycle" in compiled.params.values()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.fixture
def exhibition_parent_locks():
    locked_sessions: set[Session] = set()

    def record_lock(execute_state: Any) -> None:
        if execute_state.is_select and "FOR UPDATE" in str(
            execute_state.statement.compile(dialect=postgresql.dialect())
        ):
            locked_sessions.add(execute_state.session)

    def release_lock(session: Session) -> None:
        locked_sessions.discard(session)

    event.listen(Session, "do_orm_execute", record_lock)
    event.listen(Session, "after_commit", release_lock)
    event.listen(Session, "after_rollback", release_lock)
    try:
        yield locked_sessions
    finally:
        event.remove(Session, "do_orm_execute", record_lock)
        event.remove(Session, "after_commit", release_lock)
        event.remove(Session, "after_rollback", release_lock)


@pytest.mark.parametrize("existing_run_id", [None, "pgen_reserved"])
async def test_study_ml_generation_keeps_parent_lock_through_persistence(
    exhibition_persona_db: async_sessionmaker[AsyncSession], exhibition_parent_locks: set[Session],
    monkeypatch: pytest.MonkeyPatch, existing_run_id: str | None,
) -> None:
    async with exhibition_persona_db() as session:
        if existing_run_id:
            session.add(PersonaGenerationRuns(
                id=existing_run_id, study_id="std_lifecycle", user_id="usr_lifecycle", status="pending",
            ))
            await session.commit()

        async def generate(**kwargs: Any) -> list[GeneratedPersonaDraft]:
            assert session.sync_session in exhibition_parent_locks
            return [GeneratedPersonaDraft(name="Selected synthetic person", personality={})]

        def check_flush(sync_session: Session, flush_context: Any, instances: Any) -> None:
            if any(isinstance(entity, Personas) for entity in sync_session.new):
                assert sync_session in exhibition_parent_locks

        event.listen(session.sync_session, "before_flush", check_flush)
        monkeypatch.setattr(service_module, "generate_personas_for_study", generate)
        service = PersonaGenerationService(session, ml_generator=Mock(spec=service_module.MLPersonaAdapter))
        run, personas = await service.create_generation_run(
            "std_lifecycle", user_id="usr_lifecycle", target_count=1, existing_run_id=existing_run_id,
        )
        assert run.status == "completed"
        assert len(personas) == 1
        assert (await session.scalars(select(PersonaGenerationRuns.id))).all() == [run.id]
        if existing_run_id:
            assert run.id == existing_run_id


async def test_pending_study_run_blocks_an_unreserved_generation(
    exhibition_persona_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate = AsyncMock()
    monkeypatch.setattr(service_module, "generate_personas_for_study", generate)
    async with exhibition_persona_db() as session:
        session.add(PersonaGenerationRuns(
            id="pgen_busy", study_id="std_lifecycle", user_id="usr_lifecycle", status="pending",
        ))
        await session.commit()
        with pytest.raises(ValueError, match="already in progress"):
            await PersonaGenerationService(session).create_generation_run(
                "std_lifecycle", user_id="usr_lifecycle", target_count=1,
            )
        assert not session.in_transaction()
        generate.assert_not_awaited()


async def test_legacy_study_generation_releases_transaction_before_model_call(
    exhibition_persona_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with exhibition_persona_db() as session:
        async def generate(**kwargs: Any) -> list[GeneratedPersonaDraft]:
            assert not session.in_transaction()
            return [GeneratedPersonaDraft(name="Legacy synthetic person", personality={})]

        monkeypatch.setattr(service_module, "generate_personas_for_study", generate)
        run, personas = await PersonaGenerationService(session, llm_service=Mock()).create_generation_run(
            "std_lifecycle", user_id="usr_lifecycle", target_count=1,
        )
        assert run.status == "completed"
        assert len(personas) == 1


async def test_study_integrity_failure_rolls_back_personas_and_records_failed_run(
    exhibition_persona_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate = AsyncMock(return_value=[GeneratedPersonaDraft(name="Rejected synthetic person", personality={})])
    monkeypatch.setattr(service_module, "generate_personas_for_study", generate)
    async with exhibition_persona_db() as session:
        def reject_persona(sync_session: Session, flush_context: Any, instances: Any) -> None:
            if any(isinstance(entity, Personas) for entity in sync_session.new):
                raise IntegrityError("persona insert", {}, ValueError("test constraint"))

        event.listen(session.sync_session, "before_flush", reject_persona)
        with pytest.raises(APIError) as raised:
            await PersonaGenerationService(
                session, ml_generator=Mock(spec=service_module.MLPersonaAdapter),
            ).create_generation_run("std_lifecycle", user_id="usr_lifecycle", target_count=1)
        assert raised.value.status_code == 409
        assert raised.value.error_code == "data_integrity"
    async with exhibition_persona_db() as session:
        assert not (await session.scalars(select(Personas.id))).all()
        run = (await session.scalars(select(PersonaGenerationRuns))).one()
        assert run.status == "failed"
        assert run.generated_count == 0


async def test_regeneration_keeps_parent_lock_until_new_version_is_saved(
    exhibition_run_artifacts: async_sessionmaker[AsyncSession], exhibition_parent_locks: set[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with exhibition_run_artifacts() as session:
        persona = await session.get(Personas, "per_keep")
        assert persona is not None
        persona.segment_id = "seg_new_1"
        await session.commit()

        async def generate(**kwargs: Any) -> list[GeneratedPersonaDraft]:
            assert session.sync_session in exhibition_parent_locks
            assert "per_keep" in kwargs["exclude_names"]
            assert "per_foreign" not in kwargs["exclude_names"]
            assert "per_other_context" not in kwargs["exclude_names"]
            return [GeneratedPersonaDraft(name="Replacement synthetic person", personality={})]

        def check_flush(sync_session: Session, flush_context: Any, instances: Any) -> None:
            if any(isinstance(entity, Personas) for entity in sync_session.dirty):
                assert sync_session in exhibition_parent_locks

        event.listen(session.sync_session, "before_flush", check_flush)
        monkeypatch.setattr(service_module, "generate_personas_for_study", generate)
        regenerated = await PersonaGenerationService(
            session, ml_generator=Mock(spec=service_module.MLPersonaAdapter),
        ).regenerate_persona("std_lifecycle", "per_keep", "usr_lifecycle")
        assert regenerated.version == 2
        assert regenerated.name == "Replacement synthetic person"


@pytest.fixture
async def exhibition_dataset(
    exhibition_persona_db: async_sessionmaker[AsyncSession], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    monkeypatch.setattr(dataset_module, "_upload_dir", lambda: tmp_path)
    owned_file = tmp_path / "ds_lifecycle.json"
    owned_file.write_text("[]", encoding="utf-8")
    async with exhibition_persona_db() as session:
        session.add(DatasetSources(
            id="ds_lifecycle", user_id="usr_lifecycle", name="Synthetic dataset",
            file_path=str(owned_file), status="ready",
            segments=[{"id": "dataset_segment", "name": "Synthetic segment", "population_share": 1.0,
                       "population_count": 10, "population_percentage": 100.0, "constraints": {}}],
        ))
        await session.commit()
    return owned_file


async def test_dataset_delete_keeps_owned_file_if_database_commit_fails(
    exhibition_persona_db: async_sessionmaker[AsyncSession], exhibition_dataset: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with exhibition_persona_db() as session:
        monkeypatch.setattr(session, "commit", AsyncMock(side_effect=RuntimeError("commit rejected")))
        service = DatasetService(Mock(return_value=session))
        with pytest.raises(RuntimeError, match="commit rejected"):
            await service.delete_dataset("ds_lifecycle", "usr_lifecycle")
    assert exhibition_dataset.read_text(encoding="utf-8") == "[]"
    async with exhibition_persona_db() as session:
        assert await session.get(DatasetSources, "ds_lifecycle") is not None


@pytest.mark.parametrize("stored_path_kind", ["owned", "another_dataset", "outside_root"])
async def test_dataset_delete_unlinks_only_its_canonical_file_after_commit(
    exhibition_persona_db: async_sessionmaker[AsyncSession], exhibition_dataset: Path,
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stored_path_kind: str,
) -> None:
    stored_path = {
        "owned": exhibition_dataset,
        "another_dataset": tmp_path / "ds_someone_else.json",
        "outside_root": tmp_path / "outside" / "ds_lifecycle.json",
    }[stored_path_kind]
    stored_path.parent.mkdir(exist_ok=True)
    stored_path.write_text("[]", encoding="utf-8")
    async with exhibition_persona_db() as session:
        dataset = await session.get(DatasetSources, "ds_lifecycle")
        assert dataset is not None
        dataset.file_path = str(stored_path)
        await session.commit()

    committed: list[bool] = []
    real_remove = dataset_module.os.remove

    def on_commit(session: Session) -> None:
        committed.append(True)

    def remove_after_commit(path: Any) -> None:
        assert committed, "The file must not be unlinked before the database commit"
        real_remove(path)

    event.listen(Session, "after_commit", on_commit)
    monkeypatch.setattr(dataset_module.os, "remove", remove_after_commit)
    try:
        assert await DatasetService(exhibition_persona_db).delete_dataset("ds_lifecycle", "usr_lifecycle")
    finally:
        event.remove(Session, "after_commit", on_commit)
    assert stored_path.exists() is (stored_path_kind != "owned")
    async with exhibition_persona_db() as session:
        assert await session.get(DatasetSources, "ds_lifecycle") is None


async def test_dataset_delete_rejects_foreign_owner_without_unlinking(
    exhibition_persona_db: async_sessionmaker[AsyncSession], exhibition_dataset: Path,
) -> None:
    assert not await DatasetService(exhibition_persona_db).delete_dataset("ds_lifecycle", "usr_other_lifecycle")
    assert exhibition_dataset.exists()


@pytest.fixture
def exhibition_dataset_selection(exhibition_parent_locks: set[Session]) -> AsyncMock:
    async def generate_segment(
        dataset: DatasetSources, segment: dict[str, Any], count: int,
        business_name: str, business_description: str, study_context: dict[str, Any],
        claims: list[dict[str, Any]], exclude_ids: set[str], exclude_names: set[str],
    ) -> list[dict[str, Any]]:
        assert exhibition_parent_locks, "CPU selection must run under the parent lock"
        record_id = next(record_id for record_id in ("source-one", "source-two") if record_id not in exclude_ids)
        return [{
            "name": record_id, "age": 30, "occupation": "Planner", "personality": {},
            "served_by": "bebshax-persona-ml/fixture", "segment_id": segment["id"],
            "segment_name": segment["name"],
            "detailed_attributes": {"ml_provenance": {"record_id": record_id}},
            "validation": {"status": "VALID", "violations": [], "warnings": []},
        }]

    return AsyncMock(side_effect=generate_segment)


@pytest.mark.parametrize("study_id", [None, "std_lifecycle"])
async def test_dataset_selection_and_persistence_share_parent_lock(
    exhibition_persona_db: async_sessionmaker[AsyncSession], exhibition_dataset: Path,
    exhibition_parent_locks: set[Session], exhibition_dataset_selection: AsyncMock,
    monkeypatch: pytest.MonkeyPatch, study_id: str | None,
) -> None:
    service = DatasetService(exhibition_persona_db, ml_generator=Mock(spec=service_module.MLPersonaAdapter))
    monkeypatch.setattr(service, "_generate_ml_segment", exhibition_dataset_selection)

    def check_flush(session: Session, flush_context: Any, instances: Any) -> None:
        if any(isinstance(entity, Personas) for entity in session.new):
            assert session in exhibition_parent_locks

    event.listen(Session, "before_flush", check_flush)
    try:
        first = await service.generate_personas_from_dataset(
            "ds_lifecycle", requested_count=1, user_id="usr_lifecycle", study_id=study_id,
        )
        second = await service.generate_personas_from_dataset(
            "ds_lifecycle", requested_count=1, user_id="usr_lifecycle", study_id=study_id,
        )
    finally:
        event.remove(Session, "before_flush", check_flush)
    assert first["personas"][0]["name"] != second["personas"][0]["name"]
    async with exhibition_persona_db() as session:
        for response in (first, second):
            persisted = await session.get(Personas, response["personas"][0]["id"])
            assert persisted is not None
            assert persisted.generation_run_id == response["run_id"]
            assert persisted.owner_id == "usr_lifecycle"
        dataset = await session.get(DatasetSources, "ds_lifecycle")
        assert dataset is not None and dataset.persona_count_generated == 2
        if study_id:
            study = await session.get(Studies, study_id)
            assert study is not None and study.persona_count == 2


async def test_dataset_integrity_failure_leaves_no_run_or_partial_personas(
    exhibition_persona_db: async_sessionmaker[AsyncSession], exhibition_dataset: Path,
    exhibition_dataset_selection: AsyncMock, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DatasetService(exhibition_persona_db, ml_generator=Mock(spec=service_module.MLPersonaAdapter))
    monkeypatch.setattr(service, "_generate_ml_segment", exhibition_dataset_selection)

    def reject_persona(session: Session, flush_context: Any, instances: Any) -> None:
        if any(isinstance(entity, Personas) for entity in session.new):
            raise IntegrityError("persona insert", {}, ValueError("test constraint"))

    event.listen(Session, "before_flush", reject_persona)
    try:
        with pytest.raises(APIError) as raised:
            await service.generate_personas_from_dataset(
                "ds_lifecycle", requested_count=1, user_id="usr_lifecycle", study_id="std_lifecycle",
            )
        assert raised.value.status_code == 409
        assert raised.value.error_code == "data_integrity"
    finally:
        event.remove(Session, "before_flush", reject_persona)
    async with exhibition_persona_db() as session:
        assert not (await session.scalars(select(Personas.id))).all()
        assert not (await session.scalars(select(DatasetPersonaRuns.id))).all()
        dataset = await session.get(DatasetSources, "ds_lifecycle")
        assert dataset is not None and dataset.persona_count_generated == 0


async def test_legacy_dataset_generation_does_not_hold_parent_lock_during_model_call(
    exhibition_persona_db: async_sessionmaker[AsyncSession], exhibition_dataset: Path,
    exhibition_parent_locks: set[Session],
) -> None:
    async def complete(request: Any) -> SimpleNamespace:
        assert not exhibition_parent_locks
        return SimpleNamespace(
            text=json.dumps({"name": "Legacy synthetic person", "age": 30, "occupation": "Planner"}),
            provider="fake", model="fixture",
        )

    llm = Mock(complete=AsyncMock(side_effect=complete))
    response = await DatasetService(exhibition_persona_db, llm=llm).generate_personas_from_dataset(
        "ds_lifecycle", requested_count=1, user_id="usr_lifecycle", study_id="std_lifecycle",
    )
    assert response["generated_count"] == 1


@pytest.fixture
def exhibition_role_request(
    exhibition_persona_db: async_sessionmaker[AsyncSession], ml_training_records: list[Any],
    exhibition_parent_locks: set[Session],
) -> Request:
    async def generate(
        context: Any, count: int, *, exclude_ids: set[str], exclude_names: set[str],
    ) -> list[SimpleNamespace]:
        assert exhibition_parent_locks, "Role selection must run under the study lock"
        available = [record for record in ml_training_records if record.record_id not in exclude_ids
                     and record.name not in exclude_names]
        return [SimpleNamespace(record=record, score=0.5, topic=0, model_version="fixture", warnings=[])
                for record in available[:count]]

    app = SimpleNamespace(state=SimpleNamespace(
        db_sessionmaker=exhibition_persona_db,
        persona_ml=SimpleNamespace(generate=AsyncMock(side_effect=generate)),
    ))
    return Request({"type": "http", "app": app})


@pytest.fixture
def exhibition_role_body() -> copilot_module.GeneratePersonasRequest:
    return copilot_module.GeneratePersonasRequest(
        study_id="std_lifecycle", study_prompt="Meal and study planning for synthetic participants",
        roles=[copilot_module.PersonaGenerationRole(
            id="role_planner", role="Planner", description="Plans meals and study", selected=True, count=1,
        )],
    )


async def test_role_generation_excludes_active_sources_and_archives_only_owned_context(
    exhibition_run_artifacts: async_sessionmaker[AsyncSession], exhibition_role_request: Request,
    exhibition_role_body: copilot_module.GeneratePersonasRequest, exhibition_parent_locks: set[Session],
) -> None:
    async with exhibition_run_artifacts() as session:
        existing = await session.get(Personas, "per_delete")
        foreign = await session.get(Personas, "per_foreign")
        assert existing is not None and foreign is not None
        existing.name = "Test Person 0"
        existing.detailed_attributes = {"ml_provenance": {"record_id": "fixture-0"}}
        foreign.name = "Test Person 1"
        foreign.detailed_attributes = {"ml_provenance": {"record_id": "fixture-1"}}
        await session.commit()

    def check_flush(session: Session, flush_context: Any, instances: Any) -> None:
        if any(isinstance(entity, Personas) for entity in session.new):
            assert session in exhibition_parent_locks

    event.listen(Session, "before_flush", check_flush)
    try:
        response = await unwrap(copilot_module.generate_study_personas)(
            body=exhibition_role_body, request=exhibition_role_request, current_user=Users(id="usr_lifecycle"),
        )
    finally:
        event.remove(Session, "before_flush", check_flush)
    assert response.personas[0]["detailed_attributes"]["ml_provenance"]["record_id"] == "fixture-1"
    async with exhibition_run_artifacts() as session:
        existing = await session.get(Personas, "per_delete")
        foreign = await session.get(Personas, "per_foreign")
        other_context = await session.get(Personas, "per_other_context")
        assert existing is not None and existing.status == "archived"
        assert foreign is not None and foreign.status == "ready"
        assert other_context is not None and other_context.status == "ready"
        study = await session.get(Studies, "std_lifecycle")
        assert study is not None and study.persona_count == 1
        assert study.persona_ids == [response.personas[0]["id"]]
        assert await session.get(Personas, response.personas[0]["id"]) is not None


async def test_role_generation_requires_database_for_a_persisted_study(
    exhibition_role_request: Request, exhibition_role_body: copilot_module.GeneratePersonasRequest,
) -> None:
    exhibition_role_request.app.state.db_sessionmaker = None
    with pytest.raises(APIError) as raised:
        await unwrap(copilot_module.generate_study_personas)(
            body=exhibition_role_body, request=exhibition_role_request, current_user=Users(id="usr_lifecycle"),
        )
    assert raised.value.status_code == 503
    assert raised.value.error_code == "database_unavailable"
    exhibition_role_request.app.state.persona_ml.generate.assert_not_awaited()


async def test_role_integrity_failure_does_not_archive_previous_personas(
    exhibition_run_artifacts: async_sessionmaker[AsyncSession], exhibition_role_request: Request,
    exhibition_role_body: copilot_module.GeneratePersonasRequest,
) -> None:
    def reject_persona(session: Session, flush_context: Any, instances: Any) -> None:
        if any(isinstance(entity, Personas) for entity in session.new):
            raise IntegrityError("persona insert", {}, ValueError("test constraint"))

    event.listen(Session, "before_flush", reject_persona)
    try:
        with pytest.raises(APIError) as raised:
            await unwrap(copilot_module.generate_study_personas)(
                body=exhibition_role_body, request=exhibition_role_request, current_user=Users(id="usr_lifecycle"),
            )
        assert raised.value.status_code == 409
        assert raised.value.error_code == "data_integrity"
    finally:
        event.remove(Session, "before_flush", reject_persona)
    async with exhibition_run_artifacts() as session:
        existing = await session.get(Personas, "per_delete")
        study = await session.get(Studies, "std_lifecycle")
        assert existing is not None and existing.status == "ready"
        assert study is not None and study.persona_count == 2