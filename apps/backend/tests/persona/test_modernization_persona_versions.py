"""Append-only persona lineage and caller-owned persistence transactions."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Select, event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from bebshax.api.limiter import limiter
from bebshax.api.copilot import router as copilot_router
from bebshax.api.personas import router as persona_router
from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base, Businesses, MarketSegments, Personas, Studies
from bebshax.persona.orm import PersonaAttributes, PersonaDetails, PersonaEvidence
from bebshax.persona.schema import EvidenceItem, PersonaAttribute, PersonaProfile, ProvenanceClass
from bebshax.persona.store import load_persona, save_persona
from bebshax.personas.orm import PersonaVersions
from bebshax.personas.generator import GeneratedPersonaDraft
from bebshax.personas.service import (
    PersonaGenerationService, get_persona_version, list_persona_versions, record_persona_version,
)


@pytest.fixture
async def version_sessions(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'versions.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def enforce_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add(Users(id="version-owner", email="versions@example.test", full_name="Owner", is_verified=True))
        await session.flush()
        session.add(Businesses(id="version-business", owner_id="version-owner", name="Business"))
        session.add(Studies(id="version-study", user_id="version-owner", title="Versioned study"))
        session.add(MarketSegments(
            id="version-segment", study_id="version-study", user_id="version-owner",
            segmentation_run_id="seg-run", name="Teachers", description="Synthetic teacher sources",
            population_percentage=100,
        ))
        await session.commit()
    try:
        yield sessions
    finally:
        await engine.dispose()


@pytest.fixture
def version_profile() -> PersonaProfile:
    return PersonaProfile(
        id="version-persona", business_id="version-business", name="Original source",
        age=31, occupation="Teacher", location="Austin", income_range="Unknown",
        education="College", description="Synthetic teacher source description.",
        detailed_attributes={"ml_provenance": {"record_id": "source-original"}},
    )


async def test_save_without_commit_rolls_back_persona_and_version(version_sessions, version_profile) -> None:
    async with version_sessions() as session:
        await save_persona(session, version_profile, owner_id="version-owner", commit=False)
        assert await session.get(PersonaVersions, (version_profile.id, 1)) is not None
        await session.rollback()
    async with version_sessions() as session:
        assert await session.get(Personas, version_profile.id) is None
        assert await session.get(PersonaVersions, (version_profile.id, 1)) is None


async def test_save_versions_preserves_original_and_full_legacy_profile(version_sessions, version_profile) -> None:
    async with version_sessions() as session:
        await save_persona(session, version_profile, owner_id="version-owner")
        changed = version_profile.model_copy(update={"version": 2, "name": "Replacement source"})
        await save_persona(session, changed, owner_id="version-owner")
        versions = await list_persona_versions(session, version_profile.id, owner_id="version-owner")
        assert [version.version for version in versions] == [1, 2]
        assert [version.snapshot["name"] for version in versions] == ["Original source", "Replacement source"]
        assert versions[0].legacy_profile == version_profile.model_dump(mode="json")
        assert (await load_persona(session, version_profile.id)).name == "Replacement source"
        assert await list_persona_versions(session, version_profile.id, owner_id="foreign-owner") == []
        assert await get_persona_version(session, version_profile.id, 1, owner_id="foreign-owner") is None


async def test_saved_profile_read_preserves_complete_attribute_and_evidence_provenance(
    version_sessions, version_profile,
) -> None:
    profile = version_profile.model_copy(update={
        "origin_country": "US",
        "attributes": [PersonaAttribute(
            key="goal", value="Compare complete meal options", provenance_class=ProvenanceClass.INFERRED,
            evidence_ids=["profile-evidence"], confidence=0.6, grounding_basis="contested_evidence",
        )],
        "evidence": [EvidenceItem(
            id="profile-evidence", source="synthetic-fixture", text="Complete evidence " * 200 + "evidence-tail",
            confidence=0.7,
        )],
    })
    async with version_sessions() as session:
        await save_persona(session, profile, owner_id="version-owner")
    async with version_sessions() as session:
        loaded = await load_persona(session, profile.id)
        assert loaded is not None
        assert loaded.model_dump(mode="json") == profile.model_dump(mode="json")


async def test_same_version_cannot_overwrite_existing_identity(version_sessions, version_profile) -> None:
    async with version_sessions() as session:
        await save_persona(session, version_profile, owner_id="version-owner")
        with pytest.raises(ValueError, match="version"):
            await save_persona(
                session, version_profile.model_copy(update={"name": "Overwrite"}), owner_id="version-owner",
            )
        await session.rollback()
        assert (await session.get(Personas, version_profile.id)).name == "Original source"


async def test_explicit_save_owner_cannot_be_overridden_by_profile_data(version_sessions, version_profile) -> None:
    profile = version_profile.model_copy(update={"owner_id": "foreign-owner"})
    async with version_sessions() as session:
        await save_persona(session, profile, owner_id="version-owner")
        assert (await session.get(Personas, profile.id)).owner_id == "version-owner"
        assert (await session.get(PersonaVersions, (profile.id, 1))).owner_id == "version-owner"


async def test_current_snapshot_does_not_invent_missing_historical_versions(version_sessions) -> None:
    async with version_sessions() as session:
        persona = Personas(id="historical-persona", owner_id="version-owner", name="Available version", version=4)
        session.add(persona)
        await session.flush()
        await record_persona_version(session, persona, capture_kind="observed_current")
        persona.version = 5
        persona.name = "New version"
        await record_persona_version(session, persona)
        await session.commit()
        versions = await list_persona_versions(session, persona.id, owner_id="version-owner")
        assert [version.version for version in versions] == [4, 5]
        assert versions[0].capture_kind == "observed_current"
        assert await get_persona_version(session, persona.id, 1, owner_id="version-owner") is None


async def test_version_snapshot_is_immutable(version_sessions, version_profile) -> None:
    async with version_sessions() as session:
        await save_persona(session, version_profile, owner_id="version-owner")
        version = await session.get(PersonaVersions, (version_profile.id, 1))
        with pytest.raises(ValueError, match="immutable"):
            version.snapshot = {"name": "Tampered"}
            await session.flush()
        await session.rollback()
        stored = (await session.scalars(select(PersonaVersions))).one()
        assert stored.snapshot["name"] == "Original source"


async def test_study_generation_records_versions_and_canonical_state(version_sessions, monkeypatch) -> None:
    draft = GeneratedPersonaDraft(name="New study source", segment_id="version-segment")
    monkeypatch.setattr("bebshax.personas.service.generate_personas_for_study", AsyncMock(return_value=[draft]))
    async with version_sessions() as session:
        service = PersonaGenerationService(session, ml_generator=object())
        _run, personas = await service.create_generation_run("version-study", user_id="version-owner", target_count=1)
        persona = personas[0]
        snapshot = await get_persona_version(session, persona.id, 1, owner_id="version-owner")
        assert snapshot is not None
        assert snapshot.snapshot["name"] == draft.name
        study = await session.get(Studies, "version-study")
        assert study.persona_count == 1
        assert study.persona_ids == [persona.id]
        assert [item["id"] for item in study.personas_data] == [persona.id]


async def test_regeneration_retains_original_and_refreshes_study_snapshot(version_sessions, monkeypatch) -> None:
    draft = GeneratedPersonaDraft(name="Regenerated source", segment_id="version-segment")
    monkeypatch.setattr("bebshax.personas.service.generate_personas_for_study", AsyncMock(return_value=[draft]))
    async with version_sessions() as session:
        session.add(Personas(
            id="regenerated", study_id="version-study", user_id="version-owner", owner_id="version-owner",
            segment_id="version-segment", name="Original study source", version=3,
        ))
        await session.commit()
        service = PersonaGenerationService(session, ml_generator=object())
        persona = await service.regenerate_persona("version-study", "regenerated", user_id="version-owner")
        versions = await list_persona_versions(session, persona.id, owner_id="version-owner")
        assert [item.version for item in versions] == [3, 4]
        assert [item.snapshot["name"] for item in versions] == ["Original study source", "Regenerated source"]
        study = await session.get(Studies, "version-study")
        assert study.personas_data[0]["name"] == "Regenerated source"
        assert study.personas_data[0]["version"] == 4


@pytest.mark.parametrize("shared", [False, True])
async def test_business_generation_selects_and_saves_under_one_parent_lock(
    version_sessions, version_profile, shared,
) -> None:
    business_id = "shared-business" if shared else "version-business"
    async with version_sessions() as session:
        session.add_all([
            Users(id="usr_system_holder", email="system@example.test", full_name="System"),
            Users(id="foreign-owner", email="foreign@example.test", full_name="Foreign"),
        ])
        await session.flush()
        if shared:
            session.add(Businesses(id=business_id, owner_id="usr_system_holder", name="Shared business"))
            await session.flush()
        session.add_all([
            Personas(
                id="prior-owned", business_id=business_id, owner_id="version-owner", name="Earlier source",
                detailed_attributes={"ml_provenance": {"record_id": "owned-source"}},
            ),
            Personas(
                id="prior-foreign", business_id=business_id, owner_id="foreign-owner", name="Private source",
                detailed_attributes={"ml_provenance": {"record_id": "private-source"}},
            ),
        ])
        await session.commit()
    parent_reads: list[tuple[Session, str]] = []
    persona_writers: list[Session] = []

    def observe_parent(execution) -> None:
        statement = execution.statement
        if isinstance(statement, Select) and any(
            column.get("entity") is Businesses for column in statement.column_descriptions
        ):
            parent_reads.append((execution.session, str(statement.compile(dialect=postgresql.dialect()))))

    def observe_flush(session, _context, _instances) -> None:
        if any(isinstance(item, Personas) and item.id == version_profile.id for item in session.new):
            persona_writers.append(session)

    async def select_profile(**arguments):
        parent_session, statement = parent_reads[-1]
        assert "FOR UPDATE" in statement
        assert parent_session.in_transaction()
        assert arguments["exclude_ids"] == {"owned-source"}
        assert arguments["exclude_names"] == {"Earlier source"}
        return version_profile.model_copy(update={"business_id": business_id})

    app = FastAPI()
    app.state.db_sessionmaker = version_sessions
    app.state.limiter = limiter
    app.state.persona_engine = SimpleNamespace(generate=select_profile)
    app.include_router(persona_router, prefix="/api")
    event.listen(Session, "do_orm_execute", observe_parent)
    event.listen(Session, "before_flush", observe_flush)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/api/businesses/{business_id}/personas", json={}, headers={
                "Authorization": f"Bearer {create_access_token('version-owner')}",
            })
        assert response.status_code == 201
        assert persona_writers == [parent_reads[-1][0]]
    finally:
        event.remove(Session, "do_orm_execute", observe_parent)
        event.remove(Session, "before_flush", observe_flush)
    async with version_sessions() as session:
        assert (await session.get(PersonaVersions, (version_profile.id, 1))).owner_id == "version-owner"
        business = await session.get(Businesses, business_id)
        assert business.owner_id == ("usr_system_holder" if shared else "version-owner")


async def test_study_persona_reads_use_owner_not_mutable_user_stamp(version_sessions) -> None:
    async with version_sessions() as session:
        session.add(Users(id="foreign-owner", email="foreign-read@example.test", full_name="Foreign"))
        await session.flush()
        session.add_all([
            Personas(
                id="correct-owner", study_id="version-study", user_id=None,
                owner_id="version-owner", name="Canonical owner",
            ),
            Personas(
                id="spoofed-user", study_id="version-study", user_id="version-owner",
                owner_id="foreign-owner", name="Foreign owner",
            ),
        ])
        await session.commit()
        service = PersonaGenerationService(session, ml_generator=object())
        for owner in ("version-owner", None):
            rows = await service.list_personas("version-study", user_id=owner)
            assert [row.id for row in rows] == ["correct-owner"]
            assert await service.get_persona("version-study", "spoofed-user", user_id=owner) is None
            assert await service.get_persona("version-study", "correct-owner", user_id=owner) is not None


async def test_role_cohort_captures_outgoing_and_new_rich_versions(version_sessions, monkeypatch) -> None:
    from bebshax.api import copilot
    from bebshax.api.studies import router as studies_router

    async with version_sessions() as session:
        session.add(Personas(
            id="previous-role", study_id="version-study", owner_id="version-owner",
            name="Previous role source", version=3,
            detailed_attributes={"source_documents": {"biography": "Original full source tail"}},
        ))
        await session.commit()
    selection = SimpleNamespace(record=SimpleNamespace(record_id="new-role-source", name="New role source"))
    generator = SimpleNamespace(generate=AsyncMock(return_value=[selection]))
    monkeypatch.setattr(copilot, "get_persona_ml", lambda app: generator)
    monkeypatch.setattr(copilot, "to_workflow_persona", lambda *args, **kwargs: {
        "name": "New role source", "description": "Complete role description",
        "role_id": "meal-role", "role_title": "Teacher", "age": 34, "occupation": "Teacher",
        "demographics": {"age": 34, "occupation": "Teacher"},
        "detailed_attributes": {
            "ml_provenance": {"record_id": "new-role-source", "source": "synthetic-fixture", "revision": "v1"},
            "source_documents": {"biography": "Complete new source tail"},
        },
        "attributes": [{"category": "Goals", "title": "Full role goal", "provenance_class": "SYNTHETIC",
                        "evidence_ids": [], "grounding_basis": "synthetic_training_proxy"}],
        "behaviors": ["Plans meals"], "evidence_citations": [], "dataset_refs": [],
    })
    app = FastAPI()
    app.state.db_sessionmaker = version_sessions
    app.state.limiter = limiter
    app.include_router(copilot_router, prefix="/api")
    app.include_router(studies_router, prefix="/api")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/study/generate-personas", headers={
            "Authorization": f"Bearer {create_access_token('version-owner')}",
        }, json={"study_id": "version-study", "study_prompt": "Synthetic meal planning", "roles": [{
            "id": "meal-role", "role": "Teacher", "description": "Meal planner", "selected": True, "count": 1,
        }]})
        saved = await client.get("/api/studies/version-study", headers={
            "Authorization": f"Bearer {create_access_token('version-owner')}",
        })
    assert response.status_code == 200
    assert saved.status_code == 200
    restored = saved.json()["personas_data"][0]
    generated = response.json()["personas"][0]
    for field in ("attributes", "role_id", "role_title", "description", "age", "occupation"):
        assert restored.get(field) == generated[field]
    persona_id = response.json()["personas"][0]["id"]
    async with version_sessions() as session:
        old = await get_persona_version(session, "previous-role", 3, owner_id="version-owner")
        new = await get_persona_version(session, persona_id, 1, owner_id="version-owner")
        assert old is not None and new is not None
        assert old.snapshot["detailed_attributes"]["source_documents"]["biography"] == "Original full source tail"
        assert new.snapshot["detailed_attributes"]["source_documents"]["biography"] == "Complete new source tail"
        assert new.snapshot["goals"] == ["Full role goal"]
        assert (await session.get(Personas, "previous-role")).status == "archived"
        study = await session.get(Studies, "version-study")
        assert study.persona_ids == [persona_id]
        assert study.personas_data[0]["detailed_attributes"] == new.snapshot["detailed_attributes"]