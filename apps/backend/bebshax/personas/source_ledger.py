"""Transactional, parent-scoped reservations of immutable synthetic sources."""

from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.datasets.orm import DatasetVersions
from bebshax.db.models import Businesses, DatasetPersonaRuns, DatasetSources, Personas, Studies, _utcnow
from bebshax.personas.orm import PersonaSourceSelections, PersonaVersions
from bebshax.tenancy import PUBLIC_OWNER_IDS


def source_identity(snapshot: dict[str, Any]) -> tuple[str, str] | None:
    detailed = snapshot.get("detailed_attributes") or {}
    provenance = detailed.get("ml_provenance") if isinstance(detailed, dict) else None
    if not isinstance(provenance, dict):
        return None
    namespace, record_id = provenance.get("source"), provenance.get("record_id")
    if namespace is None or record_id is None:
        return None
    if any(not isinstance(value, str) or not value.strip() or len(value) > 256 for value in (namespace, record_id)):
        raise ValueError("Source identity requires complete nonempty namespace and record ID.")
    return namespace, record_id


async def _lock_scope(
    session: AsyncSession, *, owner_id: str, study_id: str | None = None,
    business_id: str | None = None, dataset_id: str | None = None,
) -> tuple[str, str, str]:
    if not isinstance(owner_id, str) or not owner_id.strip() or len(owner_id) > 64 or owner_id in PUBLIC_OWNER_IDS:
        raise ValueError("Source selection requires a private verified owner.")
    parents = [
        ("study_id", Studies, study_id, Studies.user_id),
        ("business_id", Businesses, business_id, Businesses.owner_id),
        ("dataset_id", DatasetSources, dataset_id, DatasetSources.user_id),
    ]
    selected = [parent for parent in parents if parent[2] is not None]
    if len(selected) != 1:
        raise ValueError("Exactly one source selection scope is required.")
    column_name, model, parent_id, owner_column = selected[0]
    if not isinstance(parent_id, str) or not parent_id.strip() or len(parent_id) > 64:
        raise ValueError("Source selection requires a valid parent ID.")
    allowed = [owner_id] if column_name == "study_id" else [owner_id, *PUBLIC_OWNER_IDS]
    statement = select(owner_column).where(model.id == parent_id, owner_column.in_(allowed)).with_for_update()
    parent_owner = (await session.execute(statement)).scalar_one_or_none()
    if parent_owner is None:
        raise ValueError("Source selection parent not found for this owner.")
    return column_name, parent_id, parent_owner


async def validate_dataset_origin(session: AsyncSession, persona: Personas) -> str | None:
    if persona.dataset_persona_run_id is None:
        if persona.dataset_version_id is not None or persona.dataset_segment_key is not None:
            raise ValueError("Dataset lineage requires an actual dataset persona run.")
        return None
    run = await session.get(DatasetPersonaRuns, persona.dataset_persona_run_id)
    if run is None or run.user_id != persona.owner_id or run.study_id != persona.study_id:
        raise ValueError("Dataset persona run owner and study must match the persona.")
    if run.study_id is not None:
        study = await session.get(Studies, run.study_id)
        if study is None or study.user_id != persona.owner_id:
            raise ValueError("Dataset persona study must belong to the same owner.")
    dataset = await session.get(DatasetSources, run.dataset_id)
    if (dataset is None or dataset.user_id not in (persona.owner_id, *PUBLIC_OWNER_IDS)
            or (dataset.study_id is not None and dataset.study_id != run.study_id)):
        raise ValueError("Dataset persona run must reference a consistent authorized dataset.")
    if persona.dataset_version_id is not None:
        version = await session.get(DatasetVersions, persona.dataset_version_id)
        if version is None or version.dataset_id != run.dataset_id or version.owner_id != dataset.user_id:
            raise ValueError("Dataset version must belong to the run's dataset and owner.")
        if persona.dataset_segment_key is not None:
            matches = [
                segment for segment in version.segments
                if isinstance(segment, dict) and segment.get("id") == persona.dataset_segment_key
            ]
            if len(matches) != 1:
                raise ValueError("Dataset segment must identify exactly one segment in the pinned version.")
    else:
        raise ValueError("Typed dataset personas require a pinned dataset version.")
    return run.dataset_id


async def _release_archived_sources(
    session: AsyncSession, *, owner_id: str, column_name: str, parent_id: str,
) -> None:
    await session.flush()
    archived = select(Personas.id).where(
        Personas.id == PersonaSourceSelections.persona_id,
        Personas.owner_id == PersonaSourceSelections.persona_owner_id,
        Personas.status == "archived",
    ).exists()
    await session.execute(update(PersonaSourceSelections).where(
        PersonaSourceSelections.owner_id == owner_id,
        getattr(PersonaSourceSelections, column_name) == parent_id,
        PersonaSourceSelections.released_at.is_(None), archived,
    ).values(released_at=_utcnow()))


async def acquire_source_selection(
    session: AsyncSession, version: PersonaVersions, *, owner_id: str,
    study_id: str | None = None, business_id: str | None = None, dataset_id: str | None = None,
) -> PersonaSourceSelections:
    """Acquire after authorization, in the caller's transaction; never commit independently."""
    column_name, parent_id, parent_owner = await _lock_scope(
        session, owner_id=owner_id, study_id=study_id, business_id=business_id, dataset_id=dataset_id,
    )
    await session.flush()
    persona = await session.get(Personas, version.persona_id, populate_existing=True)
    if (persona is None or persona.owner_id != version.owner_id
            or version.owner_id not in (owner_id, *PUBLIC_OWNER_IDS)
            or version.snapshot.get("owner_id") != version.owner_id):
        raise ValueError("Source selection version owner is immutable and must remain authorized.")
    if persona.version != version.version or persona.status == "archived":
        raise ValueError("Source selection requires the current active persona version.")
    if (version.study_id != persona.study_id
            or (study_id is not None and version.study_id not in (None, study_id))
            or (business_id is not None and version.snapshot.get("business_id") != business_id)):
        raise ValueError("Source selection parent is inconsistent with its immutable version.")
    if any(
        version.snapshot.get(field) != getattr(persona, field)
        for field in ("dataset_persona_run_id", "dataset_version_id", "dataset_segment_key")
    ):
        raise ValueError("Source selection dataset lineage is immutable within a persona version.")
    if dataset_id is not None and await validate_dataset_origin(session, persona) != dataset_id:
        raise ValueError("Source selection dataset must match its typed lineage.")
    identity = source_identity(version.snapshot)
    if identity is None:
        raise ValueError("Source selection cannot invent a missing source namespace or record ID.")
    if identity != source_identity({"detailed_attributes": persona.detailed_attributes}):
        raise ValueError("Source selection identity is immutable within a persona version.")
    await _release_archived_sources(session, owner_id=owner_id, column_name=column_name, parent_id=parent_id)
    scope_column = getattr(PersonaSourceSelections, column_name)
    active = (
        PersonaSourceSelections.owner_id == owner_id, scope_column == parent_id,
        PersonaSourceSelections.persona_id == version.persona_id, PersonaSourceSelections.released_at.is_(None),
    )
    existing = (await session.scalars(select(PersonaSourceSelections).where(*active))).one_or_none()
    if existing is not None and existing.persona_version == version.version:
        if (existing.source_namespace, existing.source_record_id) != identity:
            raise ValueError("Existing source selection identity is immutable.")
        return existing
    await session.execute(update(PersonaSourceSelections).where(*active).values(released_at=_utcnow()))
    selection = PersonaSourceSelections(
        id=f"psel_{uuid4().hex}", owner_id=owner_id, scope_owner_id=parent_owner,
        persona_id=version.persona_id, persona_version=version.version, persona_owner_id=version.owner_id,
        study_id=study_id, business_id=business_id, dataset_id=dataset_id,
        source_namespace=identity[0], source_record_id=identity[1], source_name=version.snapshot.get("name"),
    )
    session.add(selection)
    await session.flush()
    return selection


async def release_source_selections(
    session: AsyncSession, *, owner_id: str, study_id: str | None = None,
    business_id: str | None = None, dataset_id: str | None = None, persona_ids: set[str] | None = None,
) -> None:
    """Release only the authorized scope, preserving the reservation's version and source."""
    column_name, parent_id, _parent_owner = await _lock_scope(
        session, owner_id=owner_id, study_id=study_id, business_id=business_id, dataset_id=dataset_id,
    )
    statement = update(PersonaSourceSelections).where(
        PersonaSourceSelections.owner_id == owner_id,
        getattr(PersonaSourceSelections, column_name) == parent_id,
        PersonaSourceSelections.released_at.is_(None),
    )
    if persona_ids is not None:
        statement = statement.where(PersonaSourceSelections.persona_id.in_(persona_ids))
    await session.execute(statement.values(released_at=_utcnow()))


async def source_exclusions(
    session: AsyncSession, *, owner_id: str, study_id: str | None = None,
    business_id: str | None = None, dataset_id: str | None = None,
) -> tuple[set[str], set[str]]:
    """Read active pinned identities, including shared personas selected for this scope."""
    column_name, parent_id, _parent_owner = await _lock_scope(
        session, owner_id=owner_id, study_id=study_id, business_id=business_id, dataset_id=dataset_id,
    )
    await _release_archived_sources(session, owner_id=owner_id, column_name=column_name, parent_id=parent_id)
    rows = (await session.execute(select(
        PersonaSourceSelections.source_record_id, PersonaSourceSelections.source_name,
    ).where(
        PersonaSourceSelections.owner_id == owner_id,
        getattr(PersonaSourceSelections, column_name) == parent_id,
        PersonaSourceSelections.released_at.is_(None),
    ))).all()
    return {record_id for record_id, _name in rows}, {name for _record_id, name in rows if name}


async def synchronize_persona_source(
    session: AsyncSession, persona: Personas, version: PersonaVersions,
) -> None:
    dataset_id = await validate_dataset_origin(session, persona)
    if not persona.owner_id or persona.owner_id in PUBLIC_OWNER_IDS:
        return
    scope: dict[str, str] = {}
    if dataset_id is not None:
        scope["dataset_id"] = dataset_id
    elif persona.generation_run_id is not None and await session.get(DatasetPersonaRuns, persona.generation_run_id) is not None:
        return
    elif persona.study_id is not None:
        scope["study_id"] = persona.study_id
    elif persona.business_id is not None:
        scope["business_id"] = persona.business_id
    if not scope:
        return
    if persona.status == "archived" or source_identity(version.snapshot) is None:
        await release_source_selections(session, owner_id=persona.owner_id, persona_ids={persona.id}, **scope)
    else:
        await acquire_source_selection(session, version, owner_id=persona.owner_id, **scope)