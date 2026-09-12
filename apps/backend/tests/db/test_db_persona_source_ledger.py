"""Scoped source reservations and typed lineage on a real FK-enforcing database."""

from collections.abc import AsyncIterator
from copy import deepcopy

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.datasets.orm import DatasetVersions
from bebshax.db.engine import get_metadata
from bebshax.db.models import Businesses, DatasetPersonaRuns, DatasetSources, Personas, Studies
from bebshax.personas import orm as persona_orm
from bebshax.personas.orm import PersonaVersions
from bebshax.personas.service import record_persona_version, refresh_study_persona_state


@pytest_asyncio.fixture
async def ledger_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", hide_parameters=True)

    @event.listens_for(engine.sync_engine, "connect")
    def enforce_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(get_metadata().create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with sessions() as session:
        session.add_all([
            Users(id=owner, email=f"{owner}@example.test", full_name="Synthetic owner")
            for owner in ("source-owner", "other-owner", "usr_system_holder")
        ])
        await session.flush()
        session.add_all([
            Studies(id="source-study", user_id="source-owner", title="First study"),
            Studies(id="second-study", user_id="source-owner", title="Second study"),
            Studies(id="other-study", user_id="other-owner", title="Other owner's study"),
            Businesses(id="source-business", owner_id="source-owner", name="Private business"),
            Businesses(id="shared-business", owner_id="usr_system_holder", name="Shared business"),
            DatasetSources(id="source-dataset", user_id="source-owner", study_id="source-study", name="Dataset"),
            DatasetSources(id="other-dataset", user_id="other-owner", study_id="other-study", name="Other dataset"),
        ])
        await session.flush()
        session.add_all([
            DatasetPersonaRuns(
                id="source-dataset-run", dataset_id="source-dataset", user_id="source-owner",
                study_id="source-study", model_used="synthetic-test-model",
            ),
            DatasetPersonaRuns(
                id="other-dataset-run", dataset_id="other-dataset", user_id="other-owner",
                study_id="other-study", model_used="synthetic-test-model",
            ),
            DatasetVersions(
                id="source-dataset-version", dataset_id="source-dataset", owner_id="source-owner", version=1,
                records_hash="synthetic-records-hash", file_path="synthetic-unused.json", row_count=2,
                column_count=1, schema_metadata={}, statistics={}, segments=[{"id": "segment-key"}],
            ),
            DatasetVersions(
                id="other-dataset-version", dataset_id="other-dataset", owner_id="other-owner", version=1,
                records_hash="synthetic-other-hash", file_path="synthetic-unused.json", row_count=2,
                column_count=1, schema_metadata={}, statistics={}, segments=[{"id": "other-key"}],
            ),
        ])
        await session.commit()
    try:
        yield sessions
    finally:
        await engine.dispose()


def source_persona(identity: str = "source-persona", **overrides) -> Personas:
    values = {
        "id": identity, "owner_id": "source-owner", "study_id": "source-study", "name": identity,
        "detailed_attributes": {"ml_provenance": {
            "source": "synthetic-corpus", "record_id": "record-one", "revision": "source-revision",
            "model_version": "model-revision",
        }},
    }
    return Personas(**{**values, **overrides})


def test_personas_declare_separate_dataset_lineage() -> None:
    columns = Personas.__table__.c
    assert {"dataset_persona_run_id", "dataset_version_id", "dataset_segment_key"} <= set(columns.keys())
    assert {key.target_fullname for key in columns.dataset_version_id.foreign_keys} == {"dataset_versions.id"}
    assert "dataset_persona_runs.id" in {
        key.target_fullname for key in columns.dataset_persona_run_id.foreign_keys
    }


async def test_version_and_source_selection_commit_atomically(ledger_sessions) -> None:
    async with ledger_sessions() as session:
        persona = source_persona()
        session.add(persona)
        version = await record_persona_version(session, persona)
        selection = (await session.scalars(select(persona_orm.PersonaSourceSelections))).one()
        assert (selection.owner_id, selection.study_id, selection.persona_version) == ("source-owner", "source-study", 1)
        assert (selection.source_namespace, selection.source_record_id) == ("synthetic-corpus", "record-one")
        assert version.snapshot["detailed_attributes"] == persona.detailed_attributes
        await session.rollback()
    async with ledger_sessions() as session:
        assert await session.get(Personas, "source-persona") is None
        assert (await session.scalars(select(PersonaVersions))).all() == []
        assert (await session.scalars(select(persona_orm.PersonaSourceSelections))).all() == []


async def test_same_active_source_conflicts_only_inside_its_owner_parent_scope(ledger_sessions) -> None:
    async with ledger_sessions() as session:
        persona = source_persona()
        session.add(persona)
        await record_persona_version(session, persona)
        await session.commit()
        duplicate = source_persona("duplicate-persona")
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await record_persona_version(session, duplicate)
        await session.rollback()
        assert await session.get(Personas, "duplicate-persona") is None
        assert len((await session.scalars(select(persona_orm.PersonaSourceSelections))).all()) == 1


@pytest.mark.parametrize("owner_id,study_id", [
    ("source-owner", "second-study"), ("other-owner", "other-study"),
])
async def test_same_source_is_reusable_in_distinct_authorized_scopes(ledger_sessions, owner_id, study_id) -> None:
    async with ledger_sessions() as session:
        first = source_persona()
        second = source_persona("second-persona", owner_id=owner_id, study_id=study_id)
        session.add_all([first, second])
        await record_persona_version(session, first)
        await record_persona_version(session, second)
        await session.commit()
        assert len((await session.scalars(select(persona_orm.PersonaSourceSelections))).all()) == 2


async def test_shared_legacy_persona_can_have_two_study_selections_and_release_one(ledger_sessions) -> None:
    from bebshax.personas.source_ledger import acquire_source_selection, release_source_selections

    async with ledger_sessions() as session:
        persona = source_persona(owner_id="usr_system_holder", study_id=None)
        session.add(persona)
        version = await record_persona_version(session, persona, capture_kind="observed_current")
        first = await acquire_source_selection(session, version, owner_id="source-owner", study_id="source-study")
        second = await acquire_source_selection(session, version, owner_id="source-owner", study_id="second-study")
        await release_source_selections(session, owner_id="source-owner", study_id="source-study")
        replacement = await acquire_source_selection(session, version, owner_id="source-owner", study_id="source-study")
        await session.commit()
        await session.refresh(first)
        assert first.released_at is not None
        assert second.released_at is None and replacement.released_at is None
        assert replacement.id != first.id
        assert first.persona_version == second.persona_version == replacement.persona_version == 1
        assert first.persona_owner_id == "usr_system_holder"


@pytest.mark.parametrize("owner_id,study_id", [
    (None, "source-study"), ("", "source-study"), ("usr_system_holder", "source-study"),
    ("source-owner", "other-study"), ("other-owner", "other-study"),
])
async def test_source_selection_rejects_unknown_or_foreign_owners(ledger_sessions, owner_id, study_id) -> None:
    from bebshax.personas.source_ledger import acquire_source_selection

    async with ledger_sessions() as session:
        persona = source_persona()
        session.add(persona)
        version = await record_persona_version(session, persona)
        with pytest.raises(ValueError):
            await acquire_source_selection(session, version, owner_id=owner_id, study_id=study_id)


async def test_same_version_cannot_change_its_source_identity(ledger_sessions) -> None:
    async with ledger_sessions() as session:
        persona = source_persona()
        session.add(persona)
        await record_persona_version(session, persona)
        await session.commit()
        changed = deepcopy(persona.detailed_attributes)
        changed["ml_provenance"]["record_id"] = "substituted-source"
        persona.detailed_attributes = changed
        with pytest.raises(ValueError, match="immutable"):
            await record_persona_version(session, persona)
        await session.rollback()
        stored = await session.get(PersonaVersions, ("source-persona", 1))
        assert stored.snapshot["detailed_attributes"]["ml_provenance"]["record_id"] == "record-one"


async def test_source_selection_rejects_reparented_persona(ledger_sessions) -> None:
    from bebshax.personas.source_ledger import acquire_source_selection

    async with ledger_sessions() as session:
        persona = source_persona()
        session.add(persona)
        version = await record_persona_version(session, persona)
        persona.owner_id = "other-owner"
        persona.study_id = "other-study"
        await session.flush()
        with pytest.raises(ValueError, match="owner|immutable"):
            await acquire_source_selection(session, version, owner_id="source-owner", study_id="source-study")


async def test_replacement_releases_old_selection_but_rollback_restores_it(ledger_sessions) -> None:
    async with ledger_sessions() as session:
        persona = source_persona()
        session.add(persona)
        await record_persona_version(session, persona)
        await session.commit()
        persona.version = 2
        await record_persona_version(session, persona)
        await session.rollback()
        selections = (await session.scalars(select(persona_orm.PersonaSourceSelections))).all()
        assert len(selections) == 1 and selections[0].released_at is None
        assert await session.get(PersonaVersions, ("source-persona", 2)) is None


async def test_replacement_without_source_releases_previous_reservation(ledger_sessions) -> None:
    async with ledger_sessions() as session:
        persona = source_persona()
        session.add(persona)
        await record_persona_version(session, persona)
        persona.version = 2
        persona.detailed_attributes = {}
        await record_persona_version(session, persona)
        await session.commit()
        selections = (await session.scalars(select(persona_orm.PersonaSourceSelections))).all()
        assert len(selections) == 1 and selections[0].released_at is not None
        assert (await session.get(PersonaVersions, ("source-persona", 1))).snapshot["detailed_attributes"]["ml_provenance"]["record_id"] == "record-one"


async def test_archive_refresh_releases_source_without_deleting_history(ledger_sessions) -> None:
    async with ledger_sessions() as session:
        persona = source_persona()
        session.add(persona)
        await record_persona_version(session, persona)
        persona.status = "archived"
        study = await session.get(Studies, "source-study")
        await refresh_study_persona_state(session, study=study, owner_id="source-owner", removed_ids={persona.id})
        replacement = source_persona("replacement-persona")
        session.add(replacement)
        await record_persona_version(session, replacement)
        await session.commit()
        selections = (await session.scalars(select(persona_orm.PersonaSourceSelections))).all()
        assert len(selections) == 2
        assert sum(selection.released_at is None for selection in selections) == 1
        assert await session.get(PersonaVersions, ("source-persona", 1)) is not None


async def test_unknown_source_namespace_does_not_invent_a_ledger_identity(ledger_sessions) -> None:
    async with ledger_sessions() as session:
        persona = source_persona(detailed_attributes={"ml_provenance": {"record_id": "legacy-source"}})
        session.add(persona)
        await record_persona_version(session, persona, capture_kind="observed_current")
        await session.commit()
        assert (await session.scalars(select(persona_orm.PersonaSourceSelections))).all() == []


async def test_typed_dataset_origin_uses_actual_run_version_and_segment(ledger_sessions) -> None:
    async with ledger_sessions() as session:
        persona = source_persona(
            dataset_persona_run_id="source-dataset-run", dataset_version_id="source-dataset-version",
            dataset_segment_key="segment-key",
        )
        session.add(persona)
        version = await record_persona_version(session, persona)
        await session.commit()
        selection = (await session.scalars(select(persona_orm.PersonaSourceSelections))).one()
        assert selection.dataset_id == "source-dataset" and selection.study_id is None
        assert version.snapshot["dataset_persona_run_id"] == "source-dataset-run"
        assert version.snapshot["dataset_version_id"] == "source-dataset-version"
        assert version.snapshot["dataset_segment_key"] == "segment-key"


@pytest.mark.parametrize("field,replacement", [
    ("dataset_persona_run_id", "replacement-dataset-run"),
    ("dataset_version_id", "replacement-dataset-version"),
    ("dataset_segment_key", None),
])
async def test_direct_selection_rejects_changed_immutable_dataset_lineage(ledger_sessions, field, replacement) -> None:
    from bebshax.personas.source_ledger import acquire_source_selection

    async with ledger_sessions() as session:
        session.add_all([
            DatasetPersonaRuns(
                id="replacement-dataset-run", dataset_id="source-dataset", user_id="source-owner",
                study_id="source-study", model_used="synthetic-test-model",
            ),
            DatasetVersions(
                id="replacement-dataset-version", dataset_id="source-dataset", owner_id="source-owner", version=2,
                records_hash="synthetic-next-hash", file_path="synthetic-unused.json", row_count=2,
                column_count=1, schema_metadata={}, statistics={}, segments=[{"id": "segment-key"}],
            ),
        ])
        persona = source_persona(
            dataset_persona_run_id="source-dataset-run", dataset_version_id="source-dataset-version",
            dataset_segment_key="segment-key",
        )
        session.add(persona)
        version = await record_persona_version(session, persona)
        setattr(persona, field, replacement)

        with pytest.raises(ValueError, match="immutable"):
            await acquire_source_selection(session, version, owner_id="source-owner", dataset_id="source-dataset")


@pytest.mark.parametrize("changed", [
    {"dataset_persona_run_id": "other-dataset-run"},
    {"dataset_version_id": "other-dataset-version"},
    {"dataset_segment_key": "missing-segment"},
])
async def test_dataset_lineage_rejects_foreign_or_missing_membership(ledger_sessions, changed) -> None:
    async with ledger_sessions() as session:
        fields = {
            "dataset_persona_run_id": "source-dataset-run", "dataset_version_id": "source-dataset-version",
            "dataset_segment_key": "segment-key", **changed,
        }
        persona = source_persona(**fields)
        session.add(persona)
        with pytest.raises((ValueError, IntegrityError)):
            await record_persona_version(session, persona)
        await session.rollback()


@pytest.mark.parametrize("break_link", ["study-owner", "dataset-study", "null-dataset-owner", "null-version-owner"])
async def test_dataset_lineage_rejects_reparented_or_unattributed_parents(ledger_sessions, break_link) -> None:
    async with ledger_sessions() as session:
        if break_link == "study-owner":
            (await session.get(Studies, "source-study")).user_id = "other-owner"
        elif break_link == "dataset-study":
            (await session.get(DatasetSources, "source-dataset")).study_id = "other-study"
        elif break_link == "null-dataset-owner":
            (await session.get(DatasetSources, "source-dataset")).user_id = None
        else:
            (await session.get(DatasetVersions, "source-dataset-version")).owner_id = None
        persona = source_persona(
            dataset_persona_run_id="source-dataset-run", dataset_version_id="source-dataset-version",
            dataset_segment_key="segment-key",
        )
        session.add(persona)
        with pytest.raises(ValueError):
            await record_persona_version(session, persona)
        await session.rollback()


@pytest.mark.parametrize("dataset_owner", ["source-owner", "usr_system_holder"])
async def test_unscoped_owned_or_explicitly_shared_dataset_can_supply_private_study(ledger_sessions, dataset_owner) -> None:
    async with ledger_sessions() as session:
        dataset = await session.get(DatasetSources, "source-dataset")
        dataset.user_id, dataset.study_id = dataset_owner, None
        (await session.get(DatasetVersions, "source-dataset-version")).owner_id = dataset_owner
        persona = source_persona(
            dataset_persona_run_id="source-dataset-run", dataset_version_id="source-dataset-version",
            dataset_segment_key="segment-key",
        )
        session.add(persona)
        await record_persona_version(session, persona)
        selection = (await session.scalars(select(persona_orm.PersonaSourceSelections))).one()
        assert selection.owner_id == "source-owner" and selection.scope_owner_id == dataset_owner
        assert selection.dataset_id == "source-dataset"


async def test_legacy_dataset_alias_is_preserved_without_guessing_a_selection_scope(ledger_sessions) -> None:
    async with ledger_sessions() as session:
        persona = source_persona(generation_run_id="source-dataset-run", segment_id="segment-key")
        session.add(persona)
        version = await record_persona_version(session, persona, capture_kind="observed_current")
        assert version.snapshot["generation_run_id"] == "source-dataset-run"
        assert version.snapshot["dataset_persona_run_id"] is None
        assert (await session.scalars(select(persona_orm.PersonaSourceSelections))).all() == []


@pytest.mark.parametrize("unscoped_dataset", [False, True])
async def test_study_refresh_releases_archived_dataset_selection(ledger_sessions, unscoped_dataset) -> None:
    async with ledger_sessions() as session:
        if unscoped_dataset:
            (await session.get(DatasetSources, "source-dataset")).study_id = None
        persona = source_persona(
            dataset_persona_run_id="source-dataset-run", dataset_version_id="source-dataset-version",
            dataset_segment_key="segment-key",
        )
        session.add(persona)
        await record_persona_version(session, persona)
        persona.status = "archived"
        study = await session.get(Studies, "source-study")
        await refresh_study_persona_state(session, study=study, owner_id="source-owner", removed_ids={persona.id})
        selection = (await session.scalars(select(persona_orm.PersonaSourceSelections))).one()
        assert selection.released_at is not None


async def test_replacement_after_legacy_archive_releases_only_that_scope(ledger_sessions) -> None:
    async with ledger_sessions() as session:
        persona = source_persona()
        unrelated = source_persona("unrelated", study_id="second-study")
        session.add_all([persona, unrelated])
        await record_persona_version(session, persona)
        await record_persona_version(session, unrelated)
        persona.status = "archived"
        replacement = source_persona("replacement")
        session.add(replacement)
        await record_persona_version(session, replacement)
        await session.commit()
        active = (await session.scalars(select(persona_orm.PersonaSourceSelections).where(
            persona_orm.PersonaSourceSelections.released_at.is_(None),
        ))).all()
        assert {selection.persona_id for selection in active} == {"replacement", "unrelated"}


async def test_shared_selection_is_used_by_canonical_scoped_exclusions(ledger_sessions) -> None:
    from bebshax.personas.service import active_source_exclusions
    from bebshax.personas.source_ledger import acquire_source_selection

    async with ledger_sessions() as session:
        persona = source_persona(owner_id="usr_system_holder", study_id=None)
        session.add(persona)
        version = await record_persona_version(session, persona)
        await acquire_source_selection(session, version, owner_id="source-owner", study_id="source-study")
        excluded = await active_source_exclusions(
            session, owner_id="source-owner", scope=Personas.study_id == "source-study", study_id="source-study",
        )
        other = await active_source_exclusions(
            session, owner_id="source-owner", scope=Personas.study_id == "second-study", study_id="second-study",
        )
        assert excluded == ({"record-one"}, {"source-persona"})
        assert other == (set(), set())


@pytest.mark.parametrize("business_id", ["source-business", "shared-business"])
async def test_business_scope_rejects_duplicate_sources_even_for_a_shared_parent(ledger_sessions, business_id) -> None:
    async with ledger_sessions() as session:
        first = source_persona(study_id=None, business_id=business_id)
        session.add(first)
        await record_persona_version(session, first)
        await session.commit()
        duplicate = source_persona("business-duplicate", study_id=None, business_id=business_id)
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await record_persona_version(session, duplicate)
        await session.rollback()


async def test_dataset_scope_rejects_duplicate_sources(ledger_sessions) -> None:
    lineage = {
        "dataset_persona_run_id": "source-dataset-run", "dataset_version_id": "source-dataset-version",
        "dataset_segment_key": "segment-key",
    }
    async with ledger_sessions() as session:
        first = source_persona(**lineage)
        session.add(first)
        await record_persona_version(session, first)
        await session.commit()
        duplicate = source_persona("dataset-duplicate", **lineage)
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await record_persona_version(session, duplicate)
        await session.rollback()


@pytest.mark.parametrize("changes", [
    {"study_id": None}, {"business_id": "source-business"},
    {"owner_id": None}, {"owner_id": "usr_system_holder"},
    {"scope_owner_id": "other-owner"}, {"persona_owner_id": "other-owner"},
    {"persona_version": 77}, {"source_namespace": ""}, {"source_record_id": " "},
])
async def test_database_rejects_invalid_direct_source_selection_rows(ledger_sessions, changes) -> None:
    async with ledger_sessions() as session:
        persona = source_persona(detailed_attributes={})
        session.add(persona)
        await record_persona_version(session, persona)
        await session.commit()
        fields = {
            "id": "invalid-selection", "owner_id": "source-owner", "scope_owner_id": "source-owner",
            "persona_id": "source-persona", "persona_version": 1, "persona_owner_id": "source-owner",
            "study_id": "source-study", "source_namespace": "corpus", "source_record_id": "record", **changes,
        }
        session.add(persona_orm.PersonaSourceSelections(**fields))
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


async def test_quarantined_memories_are_not_retrievable_by_either_tenant(ledger_sessions) -> None:
    from bebshax.llm.adapters.embeddings import HashEmbedding
    from bebshax.memory.orm import MemoryItems
    from bebshax.memory.service import MemoryService

    embeddings = HashEmbedding()
    [vector] = await embeddings.embed(["Synthetic private research memory"])
    async with ledger_sessions() as session:
        session.add(source_persona())
        await session.flush()
        session.add_all([
            MemoryItems(
                id=identity, persona_id="source-persona", owner_id=owner_id, kind="episodic",
                text="Synthetic private research memory", embedding=vector, embedding_space=embeddings.space,
            )
            for identity, owner_id in (("quarantine", None), ("private-one", "source-owner"), ("private-two", "other-owner"))
        ])
        await session.commit()
    memory = MemoryService(ledger_sessions, embeddings)
    assert [item.id for item in await memory.retrieve("source-persona", "Synthetic private research memory", owner_id="source-owner")] == ["private-one"]
    assert [item.id for item in await memory.retrieve("source-persona", "Synthetic private research memory", owner_id="other-owner")] == ["private-two"]