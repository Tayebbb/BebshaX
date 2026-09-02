"""Database seed utility for BebshaX demo and integration mode (Phase 13)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bebshax.auth.models import Users
from bebshax.auth.security import hash_password
from bebshax.db.models import (
    DATA_SOURCE_CACHED,
    Businesses,
    Personas,
    LLMRequests,
    Studies,
    StudyReports,
)
from bebshax.persona.schema import (
    EvidenceItem,
    PersonaAttribute,
    PersonaProfile,
    ProvenanceClass,
)
from bebshax.persona.store import save_persona
from bebshax.tenancy import PUBLIC_OWNER_IDS

logger = logging.getLogger(__name__)


def _workflow_persona_payload(profile: PersonaProfile, study_id: str) -> dict:
    """Serialize the seeded persona into the shape ``Studies.personas_data``
    carries — the JSON the 5-step workflow reads (the same contract
    ``api/copilot.py`` persists after ``_apply_evidence_grounding``).

    Honesty mirrors the copilot pipeline with zero retrieved study evidence:
    nothing may claim OBSERVED (downgrade-only; SYNTHETIC is never upgraded)
    and grounding is 0.0 with the ``no_evidence_retrieved`` basis.
    """
    attributes = []
    for attr in profile.attributes:
        title, _, rest = attr.value.partition(": ")
        attributes.append(
            {
                "category": attr.key,
                "title": title,
                "description": rest or attr.value,
                "provenance_class": (
                    "SYNTHETIC"
                    if attr.provenance_class is ProvenanceClass.SYNTHETIC
                    else "INFERRED"
                ),
                "evidence": None,
            }
        )
    return {
        "id": profile.id,
        "business_id": profile.business_id,
        "study_id": study_id,
        "name": profile.name,
        "initials": "".join(p[0].upper() for p in profile.name.split()[:2]),
        "country_code": "US",
        "country_name": "United States",
        "status": profile.status,
        "version": profile.version,
        "archetype": profile.occupation,
        "generation_model": profile.generation_model,
        "data_source": DATA_SOURCE_CACHED,
        "demographics": {
            "age": profile.age,
            "occupation": profile.occupation,
            "location": profile.location,
            "income_bracket": profile.income_range,
            "education": profile.education,
        },
        "description": profile.description,
        "attributes": attributes,
        "consistency_score": 0.0,
        "grounding_ratio": 0.0,
        "grounding_basis": "no_evidence_retrieved",
        "evidence_claim_count": 0,
        "critic_notes": (
            "Seeded demo persona — cached walkthrough content; "
            "no study evidence was retrieved."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def ensure_shared_tenant_users(sessionmaker_: sessionmaker[AsyncSession]) -> None:
    """Guarantee a users row for every shared owner id in PUBLIC_OWNER_IDS.

    Rows like personas stamp ``owner_id`` with these ids (FK → users.id); when
    the rows are missing the insert fails and — observed live — generated
    personas silently never reach the personas table, making interviews 404.
    Runs at every startup, independent of demo seeding.
    """
    async with sessionmaker_() as session:
        for owner_id in PUBLIC_OWNER_IDS:
            if await session.get(Users, owner_id) is None:
                session.add(
                    Users(
                        id=owner_id,
                        email=f"{owner_id}@bebshax.internal",
                        full_name=f"BebshaX shared tenant ({owner_id})",
                        auth_provider="system",
                        is_active=True,
                        is_verified=True,
                    )
                )
                logger.info("created shared-tenant users row %s", owner_id)
        await session.commit()


async def seed_demo_data(sessionmaker_: sessionmaker[AsyncSession], force: bool = False) -> bool:
    """Seed initial known-good user, business, persona, studies, and provenance if database is empty and demo_mode is enabled (or force=True)."""
    from bebshax.config import get_settings
    settings = get_settings()
    if not settings.demo_mode and not force:
        logger.info("Demo data seeding skipped (demo_mode is disabled).")
        return False

    async with sessionmaker_() as session:
        count = (await session.execute(select(func.count(Businesses.id)))).scalar_one_or_none() or 0
        if count > 0:
            return False  # Already seeded or has data


        logger.info("Seeding demo user, business, personas, studies, and initial records...")

        SYSTEM_HOLDER_ID = "usr_system_holder"
        sys_user = await session.get(Users, SYSTEM_HOLDER_ID)
        if not sys_user:
            sys_user = Users(
                id=SYSTEM_HOLDER_ID,
                email="system@bebshax.internal",
                full_name="BebshaX System Data (do not treat as a real user)",
                auth_provider="system",
                is_active=True,
                is_verified=True,
            )
            session.add(sys_user)

        # 0. Seed Demo User
        user = Users(
            id="usr_sarah_founder",
            email="founder@bebshax.ai",
            full_name="Sarah Chen",
            hashed_password=hash_password("Password123!"),
            auth_provider="email",
            is_verified=True,
        )
        session.add(user)

        # 1. Seed Business
        biz_id = "biz_fintech_01"
        business = Businesses(
            id=biz_id,
            name="NovaFlow Financial",
            description="Next-generation budgeting and micro-investment app for gig workers and freelancers.",
            industry="Fintech / Personal Finance",
            target_market="Independent contractors, rideshare drivers",
            owner_id=SYSTEM_HOLDER_ID,
        )
        session.add(business)


        # 2. Seed Provenance request
        prov = LLMRequests(
            request_id="req_seed_demo_01",
            task="PERSONA_GENERATION",
            pool="reasoning",
            persona_id="per_sarah_01",
            conversation_id=None,
            routing_path=["groq/llama-3.3-70b-versatile", "pollinations/deepseek-r1"],
            attempts=[
                {
                    "attempt_number": 1,
                    "provider": "pollinations",
                    "model": "deepseek-r1",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "latency_ms": 1180.2,
                    "success": True,
                    "failure_kind": None,
                    "failure_detail": None,
                    "fallback_reason": None,
                    "notes": ["Direct route completion"],
                }
            ],
            served_by_provider="pollinations",
            request_model="deepseek-r1",
            response_model="deepseek-r1",
            input_tokens=1420,
            output_tokens=850,
            total_latency_ms=1180.2,
            success=True,
        )
        session.add(prov)

        # 3. Seed Demo Studies across all 5 steps
        demo_studies = [
            Studies(
                id="study_demo_01",
                user_id="usr_sarah_founder",
                title="Customer Discovery Study",
                type="interviews",
                goal="demand_validation",
                prompt="Student academic planner with automated study group scheduling",
                status="completed",
                step=5,
                # Only per_sarah_01 is seeded, and no conversation rows exist —
                # the walkthrough study must not claim personas or interviews
                # that a judge can then fail to find.
                persona_count=1,
                persona_ids=["per_sarah_01"],
                is_demo=True,
                duration_text="Completed • Decision report ready",
                findings={
                    "executive_summary": "[Simulated demo data] Decision report written from the seeded demo persona; no interviews were run and no number here is measured.",
                },
            ),
            Studies(
                id="study_demo_02",
                user_id="usr_sarah_founder",
                title="Pricing Sensitivity Test",
                type="ab_test",
                goal="demand_validation",
                prompt="Testing 250 BDT/month vs 500 BDT/month tier elasticity",
                status="in_progress",
                step=4,
                # per_sarah_01 is stamped study_id=study_demo_01, so THIS study
                # has zero seeded persona rows — its counts must say so.
                persona_count=0,
                persona_ids=[],
                is_demo=False,
                duration_text="In Progress • Step 4 Interviews",
            ),
            Studies(
                id="study_demo_03",
                user_id="usr_sarah_founder",
                title="Concept & Demand Validation",
                type="landing_page_test",
                goal="feature_concept_exploration",
                prompt="Evaluating calendar sync vs exam deadline notifications",
                status="in_progress",
                step=2,
                # Same as demo_02: no persona rows are seeded for this study.
                persona_count=0,
                persona_ids=[],
                is_demo=False,
                duration_text="In Progress • Step 2 Personas",
            ),
            Studies(
                id="study_demo_04",
                user_id="usr_sarah_founder",
                title="Brand Messaging Discovery",
                type="message_testing",
                goal="messaging_positioning",
                prompt="Explore pitch angles for university entrance candidates",
                status="in_progress",
                step=1,
                persona_count=0,
                persona_ids=[],
                is_demo=False,
                duration_text="Just created • Step 1 Context",
            ),
        ]
        for s in demo_studies:
            session.add(s)

        # The "finished example study" affordance points at study_demo_01, so it
        # must actually own a report. Content is explicitly labelled simulated.
        session.add(
            StudyReports(
                id="rep_seed_demo_01",
                study_id="study_demo_01",
                user_id="usr_sarah_founder",
                version=1,
                title="Customer Discovery Study — Decision Report",
                executive_summary=(
                    "[Simulated demo data] A decision report for a student academic planner with "
                    "automated study-group scheduling, written from the one seeded demo persona. "
                    "No interviews were conducted for this study and nothing below is measured — "
                    "it exists so the report view can be walked through end to end."
                ),
                key_findings=[
                    "Schedule fragmentation across class, work and study-group commitments is the "
                    "friction this study set out to explore.",
                    "Pricing expectations are untested: no willingness-to-pay evidence was collected.",
                    "Calendar privacy is an open question that the seeded persona raises but does "
                    "not answer.",
                ],
                major_risks=[
                    "Nothing here has been tested with real students, or with synthetic interviews — "
                    "this is seeded walkthrough content only.",
                ],
                recommendations=[
                    "Run the study for real: generate personas, interview them, then regenerate this report.",
                    "Validate the scheduling friction with a short survey of real students before building.",
                ],
                limitations=(
                    "Simulated demo content seeded for the walkthrough. No interviews were run — "
                    "with real or synthetic respondents — and no claim here is evidence-backed."
                ),
                metrics={"total_personas": 1, "total_interviews": 0},
                is_synthetic=True,
            )
        )

        await session.commit()

    # 3. Seed Persona Profile using save_persona
    profile = PersonaProfile(
        id="per_sarah_01",
        business_id="biz_fintech_01",
        name="Sarah Chen",
        status="active",
        version=1,
        generation_model="pollinations/deepseek-r1",
        age=29,
        occupation="Full-time Rideshare & Grocery Courier",
        location="Austin, TX (Suburban)",
        income_range="$38,000 - $46,000 / year (unpredictable)",
        education="Associate Degree in Graphic Design",
        description="Balancing three delivery platforms while building a 3-month safety buffer. Highly reliant on mobile workflow smoothing.",
        warnings=[],
        attributes=[
            PersonaAttribute(
                key="Goals",
                value="Predictable Cashflow Smoothing: Needs an automated tool that sets aside tax deductions and vehicle repair reserves immediately upon weekly payout.",
                provenance_class=ProvenanceClass.OBSERVED,
                confidence=0.94,
                evidence_ids=["ev_seed_01"],
            ),
            PersonaAttribute(
                key="Pain Points",
                value="Traditional Banking Overdraft Traps: Standard banking algorithms misjudge pending payout deposits, triggering punitive $35 overdraft fees.",
                provenance_class=ProvenanceClass.INFERRED,
                confidence=0.88,
                evidence_ids=["ev_seed_02"],
            ),
            PersonaAttribute(
                key="Behaviors",
                value="Multiple App Switching: Keeps 4 distinct apps open simultaneously while navigating shifts; needs frictionless glanceable UI.",
                provenance_class=ProvenanceClass.SYNTHETIC,
                confidence=0.91,
                evidence_ids=[],
            ),
        ],
        evidence=[
            EvidenceItem(
                id="ev_seed_01",
                source="PersonaHub (Financial Segment)",
                text="Couriers consistently mention sudden vehicle repair costs as their #1 emergency failure point.",
                type="grounding",
                relevance=0.95,
                confidence=0.94,
            ),
            EvidenceItem(
                id="ev_seed_02",
                source="EmpatheticDialogues & Customer Reviews",
                text="Overdraft fees feel punitive when weekly earnings are literally arriving the next day.",
                type="grounding",
                relevance=0.89,
                confidence=0.88,
            ),
        ],
    )

    async with sessionmaker_() as session:
        await save_persona(
            session,
            profile,
            owner_id="usr_system_holder",
            # H3 piece 2: seeded demo content must never present as live output.
            data_source=DATA_SOURCE_CACHED,
            # H3 piece 2: seeded demo content must never present as live output.
        )
        # study_demo_01 lists persona_ids=[per_sarah_01]; the persona row has to
        # actually carry that study id or the study-scoped list returns nothing
        # and the study's own persona_count becomes an unsupported claim.
        # owner_id stays with the system holder so the demo stays world-readable.
        seeded = await session.get(Personas, profile.id)
        if seeded is not None:
            seeded.study_id = "study_demo_01"
            seeded.user_id = "usr_sarah_founder"
            # The workflow view reads Studies.personas_data (no DB fallback);
            # leaving it empty made Step 5 read "Synthesized from 0 synthetic
            # personas" while the study card promised 1.
            demo_study = await session.get(Studies, "study_demo_01")
            if demo_study is not None:
                demo_study.personas_data = [
                    _workflow_persona_payload(profile, "study_demo_01")
                ]
            await session.commit()
        logger.info("Demo persona seed complete.")
    return True


