"""Database seed utility for BebshaX demo and integration mode (Phase 13).

Showcase-case contract (coherence + honesty):

- ONE Bangladesh-context business that matches the seeded studies (a student
  academic planner priced in BDT) and ONE persona consistent with it;
- evidence items are REAL records from ``data/processed`` grounding corpora,
  loaded from disk at seed time. A claim is stored OBSERVED only when its cited
  record was actually found; otherwise the citation is stripped and the claim
  is INFERRED — enforced by the same ``coerce_provenance`` the generator uses;
- a SINGLE serializer (``workflow_persona_payload``) produces the workflow's
  ``Studies.personas_data`` from the very ``PersonaProfile`` that
  ``save_persona`` writes to ``persona_attributes``/``persona_details``, so
  the two views can never disagree;
- nothing is written to ``llm_requests``: provenance rows come from real LLM
  calls only, never from a seed;
- the demo login is a documented, flag-gated fixture (``docs/DEMO.md``) and
  the demo user is a distinct person from every seeded persona.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bebshax.auth.models import Users
from bebshax.auth.security import hash_password
from bebshax.db.models import (
    DATA_SOURCE_CACHED,
    Businesses,
    Personas,
    Studies,
    StudyReports,
)
from bebshax.persona.evidence import DATASET_ROLES, MAX_STORED_CHARS
from bebshax.persona.schema import (
    EvidenceItem,
    GeneratedClaim,
    GeneratedPersona,
    PersonaProfile,
    ProvenanceClass,
    coerce_provenance,
)
from bebshax.persona.store import save_persona
from bebshax.personas.validator import _provenance_ratios
from bebshax.tenancy import PUBLIC_OWNER_IDS

logger = logging.getLogger(__name__)

SYSTEM_HOLDER_ID = "usr_system_holder"

# Flag-gated demo login (docs/DEMO.md §3). Not a secret: config refuses
# demo_mode in production/staging, and the user is a fixture, not a person.
DEMO_USER_ID = "usr_demo_founder"
DEMO_USER_EMAIL = "founder@bebshax.ai"
DEMO_USER_PASSWORD = "Password123!"
DEMO_USER_NAME = "Tanvir Rahman"  # distinct from every seeded persona by design

DEMO_BUSINESS_ID = "biz_shomoysuchi_01"
DEMO_PERSONA_ID = "per_demo_nusrat_01"
DEMO_STUDY_ID = "study_demo_01"
SEED_GENERATION_MODEL = "seed/hand-authored (no LLM call)"

# Fields a processed record may carry its citable text in (EvidenceStore parity).
_RECORD_TEXT_FIELDS = ("text", "utterance", "persona", "content", "body")


@dataclass(frozen=True)
class SeedEvidenceRef:
    """A citation into a REAL processed dataset record (never hand-written text)."""

    record_id: str
    dataset: str  # data/processed/<dataset>.jsonl — must be a grounding corpus


# Real Amazon office-products reviews about student planners (grounding corpus,
# CC-licensed slice documented in data/DATASETS.md). Verified present in the
# pinned slice on 2026-09-06; the seed re-verifies on disk every time.
_REV_UNIVERSITY_SON = SeedEvidenceRef("49f85be0-fb49-5bba-8875-c650a0ae6ba3", "amazon_reviews_office_products")
_REV_WEEKLY_MONTHLY = SeedEvidenceRef("c9775182-05c0-54ad-aaca-ec5f1c46cad3", "amazon_reviews_office_products")
_REV_DIGITIZED = SeedEvidenceRef("1e1dc9ca-fd6e-5b1d-b46b-a9cfc24f3753", "amazon_reviews_office_products")
_REV_DIGITAL_SHARED = SeedEvidenceRef("faa65d00-1be6-5eaf-b10c-538ea790263c", "amazon_reviews_office_products")

DEMO_EVIDENCE_REFS: tuple[SeedEvidenceRef, ...] = (
    _REV_UNIVERSITY_SON,
    _REV_WEEKLY_MONTHLY,
    _REV_DIGITIZED,
    _REV_DIGITAL_SHARED,
)

# The persona's claims, in the generator's own output contract. OBSERVED is a
# REQUEST here — coerce_provenance grants it only for citations found on disk.
DEMO_PERSONA_CLAIMS: dict[str, list[GeneratedClaim]] = {
    "goals": [
        GeneratedClaim(
            value="No missed deadlines: wants to finish the semester without a single missed "
            "assignment or exam-registration date",
            provenance="INFERRED",
        )
    ],
    "pain_points": [
        GeneratedClaim(
            value="Clashing commitments: study-group sessions keep colliding with class blocks "
            "and weekend tutoring hours",
            provenance="INFERRED",
        )
    ],
    "needs": [
        GeneratedClaim(
            value="Weekly and monthly views: wants the same semester as a week plan and a "
            "month overview",
            provenance="OBSERVED",
            evidence_ids=[_REV_WEEKLY_MONTHLY.record_id, _REV_DIGITIZED.record_id],
        )
    ],
    "behaviors": [
        GeneratedClaim(
            value="Plans from week one: records assignments and test schedules in a planner "
            "from the first week of classes",
            provenance="OBSERVED",
            evidence_ids=[_REV_UNIVERSITY_SON.record_id],
        )
    ],
    "technology_usage": [
        GeneratedClaim(
            value="Digital calendar plus paper: keeps a calendar shared across phone and "
            "laptop alongside a paper planner",
            provenance="OBSERVED",
            evidence_ids=[_REV_DIGITAL_SHARED.record_id, _REV_DIGITIZED.record_id],
        )
    ],
    "purchase_behavior": [
        GeneratedClaim(
            value="Price ceiling assumption: would consider about ৳250 per month only if the "
            "app replaced two others",
            provenance="SYNTHETIC",
        )
    ],
    "motivations": [
        GeneratedClaim(
            value="Own the schedule: wants to stop depending on friends' reminders for exam dates",
            provenance="SYNTHETIC",
        )
    ],
}

EVIDENCE_SCOPE_NOTE = (
    "OBSERVED claims cite real Amazon office-products reviews about student planners "
    "(reviewers outside Bangladesh) — evidence about planner-use behaviour, not about "
    "Dhaka students specifically. Validate with real local students before acting."
)
CORPUS_MISSING_NOTE = (
    "evidence corpus not present at seed time (data/processed) — every citation was "
    "stripped and OBSERVED claims were stored as INFERRED"
)


def _record_text(record: dict[str, Any]) -> str:
    return next((str(record[k]).strip() for k in _RECORD_TEXT_FIELDS if record.get(k)), "")


def load_seed_evidence(processed_dir: Path, refs: tuple[SeedEvidenceRef, ...] = DEMO_EVIDENCE_REFS) -> list[EvidenceItem]:
    """EvidenceItems for the refs that actually exist on disk, with the record's
    real text. Refs into non-grounding corpora (PersonaHub seeds, synthetic
    dialogues) are refused: those may never be cited as observation."""
    wanted: dict[str, set[str]] = {}
    for ref in refs:
        if DATASET_ROLES.get(ref.dataset, "grounding") != "grounding":
            logger.warning("seed evidence %s refused: %s is not a grounding corpus", ref.record_id, ref.dataset)
            continue
        wanted.setdefault(ref.dataset, set()).add(ref.record_id)

    found: list[EvidenceItem] = []
    for dataset, ids in wanted.items():
        path = processed_dir / f"{dataset}.jsonl"
        if not path.is_file():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not ids:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = record.get("id")
                if rid in ids:
                    text = _record_text(record)
                    if text:
                        found.append(
                            EvidenceItem(id=rid, source=dataset, text=text[:MAX_STORED_CHARS], type="dataset_record")
                        )
                    ids.discard(rid)
    return found


def build_demo_persona(evidence: list[EvidenceItem]) -> PersonaProfile:
    """The seeded persona through the generator's own provenance gate."""
    generated = GeneratedPersona(
        name="Nusrat Jahan",
        age=24,
        occupation="Third-year BBA undergraduate at a private university in Dhaka",
        location="Mohammadpur, Dhaka, Bangladesh",
        income_range="Family-supported; part-time tutoring income (amount not evidenced)",
        education="Undergraduate (BBA), in progress",
        description=(
            "Juggles a full class load, weekend tutoring and two study groups; plans on "
            "paper and on her phone and is tired of missing dates that other people knew about."
        ),
        **DEMO_PERSONA_CLAIMS,
    )
    profile = coerce_provenance(
        generated, business_id=DEMO_BUSINESS_ID, evidence=evidence, generation_model=SEED_GENERATION_MODEL
    )
    profile.id = DEMO_PERSONA_ID
    profile.status = "active"
    # Stated by the persona itself (location above) — the platform no longer
    # assumes a nationality for anyone.
    profile.country_code = "BD"
    profile.origin_country = "Bangladesh"
    profile.warnings.append(EVIDENCE_SCOPE_NOTE if evidence else CORPUS_MISSING_NOTE)
    return profile


def _claim_provenance(profile: PersonaProfile) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for attr in profile.attributes:
        grouped.setdefault(attr.key, []).append(
            {
                "value": attr.value,
                "provenance": attr.provenance_class.value,
                "evidence_ids": list(attr.evidence_ids),
                "grounding_basis": attr.grounding_basis,
            }
        )
    return grouped


def workflow_persona_payload(profile: PersonaProfile, study_id: str) -> dict[str, Any]:
    """Serialize the seeded persona into the shape ``Studies.personas_data``
    carries — the JSON the 5-step workflow reads (the contract ``api/copilot.py``
    persists after ``_apply_evidence_grounding``).

    Provenance is copied from the SAME PersonaProfile that ``save_persona``
    stores, and grounding is measured from it with the validator's ratio, so
    the workflow view and the persona tables agree by construction.
    """
    attributes = []
    for attr in profile.attributes:
        title, _, rest = attr.value.partition(": ")
        attributes.append(
            {
                "category": attr.key,
                "title": title,
                "description": rest or attr.value,
                "provenance_class": attr.provenance_class.value,
                "evidence": list(attr.evidence_ids) or None,
                "grounding_basis": attr.grounding_basis,
            }
        )
    claim_provenance = _claim_provenance(profile)
    grounding, confidence = _provenance_ratios(claim_provenance)
    observed = sum(1 for a in profile.attributes if a.provenance_class is ProvenanceClass.OBSERVED)
    return {
        "id": profile.id,
        "business_id": profile.business_id,
        "study_id": study_id,
        "name": profile.name,
        "initials": "".join(p[0].upper() for p in profile.name.split()[:2]),
        "country_code": profile.country_code,
        "country_name": profile.origin_country,
        "status": profile.status,
        "version": profile.version,
        "archetype": "University student balancing classes, tutoring and study groups",
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
        "detailed_attributes": {"claim_provenance": claim_provenance},
        "evidence": [{"id": e.id, "source": e.source, "text": e.text} for e in profile.evidence],
        "consistency_score": 0.0,
        "confidence": confidence,
        "grounding_ratio": grounding,
        "grounding_basis": "citations_verified" if observed else "no_evidence_retrieved",
        "evidence_claim_count": len(profile.evidence),
        "critic_notes": "Seeded demo persona (cached walkthrough content, no LLM call). " + " ".join(profile.warnings),
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
    """Seed the known-good demo user, business, persona and studies when the
    database is empty and demo_mode is enabled (or force=True). Idempotent:
    a populated businesses table means "already seeded" and nothing is written.
    No provenance (``llm_requests``) row is ever seeded."""
    from bebshax.config import get_settings
    settings = get_settings()
    if not settings.demo_mode and not force:
        logger.info("Demo data seeding skipped (demo_mode is disabled).")
        return False

    async with sessionmaker_() as session:
        count = (await session.execute(select(func.count(Businesses.id)))).scalar_one_or_none() or 0
        if count > 0:
            return False  # Already seeded or has data

        # Evidence is verified on disk BEFORE anything is written so the persona
        # tables and the workflow payload are built from one coerced profile.
        evidence = load_seed_evidence(settings.processed_dir_path)
        profile = build_demo_persona(evidence)
        if not evidence:
            logger.warning("demo seed: %s", CORPUS_MISSING_NOTE)

        logger.info("Seeding demo user, business, persona and studies...")

        sys_user = await session.get(Users, SYSTEM_HOLDER_ID)
        if not sys_user:
            session.add(
                Users(
                    id=SYSTEM_HOLDER_ID,
                    email="system@bebshax.internal",
                    full_name="BebshaX System Data (do not treat as a real user)",
                    auth_provider="system",
                    is_active=True,
                    is_verified=True,
                )
            )

        # 0. Demo user — the founder running the studies, not a persona.
        session.add(
            Users(
                id=DEMO_USER_ID,
                email=DEMO_USER_EMAIL,
                full_name=DEMO_USER_NAME,
                hashed_password=hash_password(DEMO_USER_PASSWORD),
                auth_provider="email",
                is_verified=True,
            )
        )

        # 1. Business — matches every seeded study (BDT-priced student planner).
        session.add(
            Businesses(
                id=DEMO_BUSINESS_ID,
                name="ShomoySuchi",
                description=(
                    "Student academic planner app for Bangladeshi university students: "
                    "class and exam calendar, automated study-group scheduling, deadline "
                    "reminders. Subscription tiers under test at ৳250 and ৳500 per month."
                ),
                industry="EdTech / Productivity",
                target_market="University students in Dhaka (public and private universities)",
                owner_id=SYSTEM_HOLDER_ID,
            )
        )

        # 2. Studies across the 5 workflow steps. Only study_demo_01 owns the
        # seeded persona and the report; the others carry counts that match
        # their (zero) rows.
        demo_studies = [
            Studies(
                id=DEMO_STUDY_ID,
                user_id=DEMO_USER_ID,
                title="Customer Discovery Study",
                type="interviews",
                goal="demand_validation",
                prompt="Student academic planner with automated study group scheduling",
                status="completed",
                step=5,
                persona_count=1,
                persona_ids=[DEMO_PERSONA_ID],
                is_demo=True,
                duration_text="Completed • Decision report ready",
                findings={
                    "executive_summary": (
                        "[Simulated demo data] Decision report written from the seeded demo "
                        "persona; no interviews were run and no number here is measured."
                    ),
                },
            ),
            Studies(
                id="study_demo_02",
                user_id=DEMO_USER_ID,
                title="Pricing Sensitivity Test",
                type="ab_test",
                goal="demand_validation",
                prompt="Testing 250 BDT/month vs 500 BDT/month tier elasticity",
                status="in_progress",
                step=4,
                persona_count=0,
                persona_ids=[],
                is_demo=False,
                duration_text="In Progress • Step 4 Interviews",
            ),
            Studies(
                id="study_demo_03",
                user_id=DEMO_USER_ID,
                title="Concept & Demand Validation",
                type="landing_page_test",
                goal="feature_concept_exploration",
                prompt="Evaluating calendar sync vs exam deadline notifications",
                status="in_progress",
                step=2,
                persona_count=0,
                persona_ids=[],
                is_demo=False,
                duration_text="In Progress • Step 2 Personas",
            ),
            Studies(
                id="study_demo_04",
                user_id=DEMO_USER_ID,
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

        observed = [a for a in profile.attributes if a.provenance_class is ProvenanceClass.OBSERVED]
        grounded_line = (
            f"{len(observed)} of {len(profile.attributes)} persona claims cite real planner reviews "
            "from the grounding corpus; the rest are inferred or explicitly assumed."
            if observed
            else "No persona claim is evidence-backed in this seed (the evidence corpus was not "
            "available), so every claim is inferred or explicitly assumed."
        )
        # The "finished example study" affordance points at study_demo_01, so it
        # must actually own a report. Content is explicitly labelled simulated.
        session.add(
            StudyReports(
                id="rep_seed_demo_01",
                study_id=DEMO_STUDY_ID,
                user_id=DEMO_USER_ID,
                version=1,
                title="Customer Discovery Study — Decision Report",
                executive_summary=(
                    "[Simulated demo data] A decision report for ShomoySuchi, a student academic "
                    "planner with automated study-group scheduling, written from the one seeded "
                    "demo persona. No interviews were conducted for this study and nothing below "
                    "is measured — it exists so the report view can be walked through end to end."
                ),
                key_findings=[
                    "Schedule fragmentation across classes, tutoring and study groups is the "
                    "friction this study set out to explore.",
                    grounded_line,
                    "Pricing expectations are untested: the ৳250/month ceiling on the persona is a "
                    "labelled assumption, not willingness-to-pay evidence.",
                ],
                major_risks=[
                    "Nothing here has been tested with real students, or with synthetic interviews — "
                    "this is seeded walkthrough content only.",
                    EVIDENCE_SCOPE_NOTE,
                ],
                recommendations=[
                    "Run the study for real: generate personas, interview them, then regenerate this report.",
                    "Validate the scheduling friction and the BDT price points with a short survey of "
                    "real Dhaka students before building.",
                ],
                limitations=(
                    "Simulated demo content seeded for the walkthrough. No interviews were run — "
                    "with real or synthetic respondents — and every OBSERVED claim traces to a "
                    "planner review, not to a Bangladeshi student."
                ),
                metrics={"total_personas": 1, "total_interviews": 0},
                is_synthetic=True,
            )
        )

        await session.commit()

    # 3. Persona — ONE coerced profile feeds both the persona tables and the
    # workflow payload (single serializer, single truth).
    async with sessionmaker_() as session:
        await save_persona(
            session,
            profile,
            owner_id=SYSTEM_HOLDER_ID,  # world-readable shared pool
            data_source=DATA_SOURCE_CACHED,  # seeded content must never present as live output
        )
        seeded = await session.get(Personas, profile.id)
        if seeded is not None:
            # study_demo_01 lists this persona; the row must carry the study id or
            # the study-scoped list returns nothing and persona_count is a lie.
            seeded.study_id = DEMO_STUDY_ID
            seeded.user_id = DEMO_USER_ID
            seeded.country_code = profile.country_code
            demo_study = await session.get(Studies, DEMO_STUDY_ID)
            if demo_study is not None:
                demo_study.personas_data = [workflow_persona_payload(profile, DEMO_STUDY_ID)]
            await session.commit()
        logger.info(
            "Demo persona seed complete: %d/%d claims OBSERVED against %d verified evidence records.",
            len(observed), len(profile.attributes), len(evidence),
        )
    return True


