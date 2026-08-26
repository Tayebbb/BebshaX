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
from bebshax.db.models import Businesses, Personas, LLMRequests, Studies
from bebshax.persona.schema import (
    EvidenceItem,
    PersonaAttribute,
    PersonaProfile,
    ProvenanceClass,
)
from bebshax.persona.store import save_persona

logger = logging.getLogger(__name__)


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
                persona_count=3,
                persona_ids=["per_sarah_01"],
                is_demo=True,
                duration_text="Completed • 3 Personas interviewed",
                findings={
                    "executive_summary": "Strong demand for automated scheduling with 84% willingness to pay among surveyed university students.",
                    "demand_signal": "High",
                    "sentiment_score": 84,
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
                persona_count=4,
                persona_ids=["per_sarah_01"],
                is_demo=True,
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
                persona_count=2,
                persona_ids=["per_sarah_01"],
                is_demo=True,
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
                is_demo=True,
                duration_text="Just created • Step 1 Context",
            ),
        ]
        for s in demo_studies:
            session.add(s)

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
        await save_persona(session, profile, owner_id="usr_system_holder")
        logger.info("Demo persona seed complete.")
    return True


