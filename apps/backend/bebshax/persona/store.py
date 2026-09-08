"""Persona/business persistence (async, session-per-request)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.db.models import Businesses, Personas
from bebshax.db.models import DATA_SOURCE_LIVE
from bebshax.persona.orm import PersonaAttributes, PersonaDetails, PersonaEvidence
from bebshax.persona.schema import EvidenceItem, PersonaAttribute, PersonaProfile, ProvenanceClass
from bebshax.tenancy import allowed_owner_ids


async def create_business(
    session: AsyncSession,
    name: str,
    description: str | None,
    owner_id: str,
    industry: str | None = None,
    target_market: str | None = None,
) -> Businesses:
    """``owner_id`` is required and has no default — see ``save_persona`` for why
    defaulting it to the system holder was a tenancy hazard (B6)."""
    business = Businesses(
        id=uuid.uuid4().hex,
        name=name,
        description=description,
        industry=industry,
        target_market=target_market,
        owner_id=owner_id,
    )
    session.add(business)
    await session.commit()
    return business


async def get_business(session: AsyncSession, business_id: str) -> Businesses | None:
    return await session.get(Businesses, business_id)


async def list_businesses(
    session: AsyncSession, owner_id: str | None = None
) -> list[Businesses]:
    query = select(Businesses).where(Businesses.owner_id.in_(allowed_owner_ids(owner_id)))
    query = query.order_by(Businesses.created_at.desc())
    result = await session.execute(query)
    return list(result.scalars())



async def save_persona(
    session: AsyncSession,
    profile: PersonaProfile,
    owner_id: str,
    data_source: str = DATA_SOURCE_LIVE,
) -> None:
    """Persist a persona.

    ``owner_id`` is REQUIRED and deliberately has no default. It used to default
    to ``"usr_system_holder"``, which is in ``PUBLIC_OWNER_IDS`` — so a caller
    that simply forgot the argument published the persona to the shared pool,
    readable by every user. That is precisely the tenancy hole B6 exists to
    close, so forgetting it is now a TypeError instead of a silent disclosure.

    ``data_source`` records how the content was produced (H3 piece 2). It
    defaults to ``"live"`` because every caller except the demo seeder reaches
    here after a real inference pass; the seeder passes ``"cached"`` explicitly.
    """
    # The Personas row is what the persona library, the interview identity card
    # and the behavioural engine read — it must carry the same facts as the
    # detail/attribute tables, otherwise every field shows as "not stated".
    grouped: dict[str, list[str]] = {}
    for attr in profile.attributes:
        grouped.setdefault(attr.key, []).append(attr.value)
    demographics = {
        key: value
        for key, value in (
            ("age", profile.age),
            ("occupation", profile.occupation),
            ("location", profile.location),
            ("income_or_budget", profile.income_range),
            ("education", profile.education),
        )
        if value not in (None, "")
    }
    session.add(
        Personas(
            id=profile.id,
            business_id=profile.business_id,
            owner_id=getattr(profile, "owner_id", None) or owner_id,
            name=profile.name,
            status=profile.status,
            version=profile.version,
            generation_model=profile.generation_model,
            data_source=data_source,
            tagline=profile.tagline,
            country_code=profile.country_code,
            bio=profile.description,
            demographics=demographics,
            personality=profile.personality.model_dump() if profile.personality else {},
            detailed_attributes=dict(profile.detailed_attributes or {}),
            goals=grouped.get("goal", []),
            pain_points=grouped.get("pain_point", []),
            needs=grouped.get("need", []),
            motivations=grouped.get("motivation", []),
            behaviors=grouped.get("behavior", []),
            preferences=grouped.get("purchase_behavior", []),
            technology_profile={"usage": grouped["technology_usage"]} if grouped.get("technology_usage") else {},
            validation_warnings=list(profile.warnings),
            evidence_citations=[
                {"id": e.id, "source": e.source, "type": e.type, "relevance": e.relevance} for e in profile.evidence
            ],
        )
    )

    session.add(
        PersonaDetails(
            persona_id=profile.id,
            age=profile.age,
            occupation=profile.occupation,
            location=profile.location,
            income_range=profile.income_range,
            education=profile.education,
            description=profile.description,
            warnings=list(profile.warnings),
        )
    )
    for attr in profile.attributes:
        session.add(
            PersonaAttributes(
                id=uuid.uuid4().hex,
                persona_id=profile.id,
                key=attr.key,
                value=attr.value,
                provenance_class=attr.provenance_class.value,
                confidence=attr.confidence,
                evidence_ids=list(attr.evidence_ids),
            )
        )
    for item in profile.evidence:
        session.add(
            PersonaEvidence(
                id=item.id,
                persona_id=profile.id,
                source=item.source,
                text=item.text,
                type=item.type,
                relevance=item.relevance,
                confidence=item.confidence,
            )
        )
    await session.commit()


async def load_persona(session: AsyncSession, persona_id: str) -> PersonaProfile | None:
    persona = await session.get(Personas, persona_id)
    details = await session.get(PersonaDetails, persona_id)
    if persona is None or details is None:
        return None
    attrs = list(
        (
            await session.execute(
                select(PersonaAttributes).where(PersonaAttributes.persona_id == persona_id)
            )
        ).scalars()
    )
    evidence = list(
        (
            await session.execute(
                select(PersonaEvidence).where(PersonaEvidence.persona_id == persona_id)
            )
        ).scalars()
    )
    return PersonaProfile(
        id=persona.id,
        business_id=persona.business_id,
        name=persona.name,
        status=persona.status,
        version=persona.version,
        generation_model=persona.generation_model,
        age=details.age,
        occupation=details.occupation,
        location=details.location,
        income_range=details.income_range,
        education=details.education,
        description=details.description,
        warnings=list(details.warnings or []),
        attributes=[
            PersonaAttribute(
                key=a.key,
                value=a.value,
                provenance_class=ProvenanceClass(a.provenance_class),
                confidence=a.confidence,
                evidence_ids=list(a.evidence_ids or []),
            )
            for a in attrs
        ],
        evidence=[
            EvidenceItem(
                id=e.id,
                source=e.source,
                text=e.text,
                type=e.type,
                relevance=e.relevance,
                confidence=e.confidence,
                timestamp=e.created_at,
            )
            for e in evidence
        ],
    )


async def list_personas(
    session: AsyncSession,
    business_id: str | None = None,
    owner_id: str | None = None,
) -> list[PersonaProfile]:
    query = select(Personas.id).order_by(Personas.created_at.desc())
    if business_id:
        query = query.where(Personas.business_id == business_id)
    query = query.where(Personas.owner_id.in_(allowed_owner_ids(owner_id)))
    persona_ids = list((await session.execute(query)).scalars().all())
    personas = []
    for pid in persona_ids:
        p = await load_persona(session, pid)
        if p:
            personas.append(p)
    return personas

