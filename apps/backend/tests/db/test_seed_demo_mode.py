import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.db.models import Base, Businesses
from bebshax.db.seed import ensure_shared_tenant_users, seed_demo_data
from bebshax.tenancy import PUBLIC_OWNER_IDS


@pytest.fixture
async def memory_sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield sm
    await engine.dispose()


@pytest.mark.asyncio
async def test_seed_demo_data_skipped_when_demo_mode_false(monkeypatch, memory_sessionmaker):
    """H3 regression guard: seed_demo_data must not insert rows when demo_mode is False."""
    from bebshax.config import Settings
    monkeypatch.setattr("bebshax.config.get_settings", lambda: Settings(demo_mode=False, jwt_secret="test_secret_at_least_32_characters_long_12345"))

    seeded = await seed_demo_data(memory_sessionmaker)
    assert seeded is False

    async with memory_sessionmaker() as session:
        count = (await session.execute(select(func.count(Businesses.id)))).scalar_one_or_none() or 0
        assert count == 0


@pytest.mark.asyncio
async def test_seed_demo_data_runs_when_demo_mode_true(monkeypatch, memory_sessionmaker):
    """H3 regression guard: seed_demo_data must insert rows when demo_mode is True."""
    from bebshax.config import Settings
    monkeypatch.setattr("bebshax.config.get_settings", lambda: Settings(demo_mode=True, jwt_secret="test_secret_at_least_32_characters_long_12345"))

    seeded = await seed_demo_data(memory_sessionmaker)
    assert seeded is True

    async with memory_sessionmaker() as session:
        count = (await session.execute(select(func.count(Businesses.id)))).scalar_one_or_none() or 0
        assert count > 0


@pytest.mark.asyncio
async def test_seed_demo_data_runs_when_forced(monkeypatch, memory_sessionmaker):
    """H3 regression guard: seed_demo_data must insert rows when force=True regardless of demo_mode."""
    from bebshax.config import Settings
    monkeypatch.setattr("bebshax.config.get_settings", lambda: Settings(demo_mode=False, jwt_secret="test_secret_at_least_32_characters_long_12345"))

    seeded = await seed_demo_data(memory_sessionmaker, force=True)
    assert seeded is True

    async with memory_sessionmaker() as session:
        count = (await session.execute(select(func.count(Businesses.id)))).scalar_one_or_none() or 0
        assert count > 0


@pytest.mark.asyncio
async def test_ensure_shared_tenant_users_creates_all_public_owner_rows(memory_sessionmaker):
    """Every PUBLIC_OWNER_IDS id must get a users row so owner_id FKs (personas etc.) can insert."""
    await ensure_shared_tenant_users(memory_sessionmaker)

    async with memory_sessionmaker() as session:
        for owner_id in PUBLIC_OWNER_IDS:
            row = await session.get(Users, owner_id)
            assert row is not None, f"missing shared-tenant users row for {owner_id}"
            assert row.auth_provider == "system"


@pytest.mark.asyncio
async def test_ensure_shared_tenant_users_is_idempotent(memory_sessionmaker):
    """Running the bootstrap twice must not fail or duplicate rows."""
    await ensure_shared_tenant_users(memory_sessionmaker)
    await ensure_shared_tenant_users(memory_sessionmaker)

    async with memory_sessionmaker() as session:
        count = (
            await session.execute(
                select(func.count(Users.id)).where(Users.id.in_(PUBLIC_OWNER_IDS))
            )
        ).scalar_one()
        assert count == len(PUBLIC_OWNER_IDS)


@pytest.mark.asyncio
async def test_demo_study_claims_match_the_rows_actually_seeded(monkeypatch, memory_sessionmaker):
    """study_demo_01 is what the "see a finished example study" link opens.

    It used to advertise "3 Personas interviewed" and metrics of 3 interviews
    while no conversation row existed for it — the honesty thesis broken on the
    product's own demo fixture.
    """
    from bebshax.config import Settings
    from bebshax.db.models import EvidenceClaims, Personas, Studies, StudyReports
    from bebshax.interview.orm import Conversations

    monkeypatch.setattr(
        "bebshax.config.get_settings",
        lambda: Settings(demo_mode=True, jwt_secret="test_secret_at_least_32_characters_long_12345"),
    )
    assert await seed_demo_data(memory_sessionmaker) is True

    async with memory_sessionmaker() as session:
        study = await session.get(Studies, "study_demo_01")
        personas = list(
            (
                await session.execute(
                    select(Personas).where(Personas.study_id == "study_demo_01")
                )
            ).scalars()
        )
        interviews = (
            await session.execute(
                select(func.count())
                .select_from(Conversations)
                .where(Conversations.study_id == "study_demo_01")
            )
        ).scalar() or 0
        claim_count = (
            await session.execute(
                select(func.count())
                .select_from(EvidenceClaims)
                .where(EvidenceClaims.study_id == "study_demo_01")
            )
        ).scalar() or 0
        report = (
            await session.execute(
                select(StudyReports).where(StudyReports.study_id == "study_demo_01")
            )
        ).scalars().first()
        all_studies = list((await session.execute(select(Studies))).scalars())
        persona_rows_by_study: dict[str, list[str]] = {}
        for s in all_studies:
            rows = list(
                (
                    await session.execute(
                        select(Personas.id).where(Personas.study_id == s.id)
                    )
                ).scalars()
            )
            persona_rows_by_study[s.id] = rows

    assert study is not None and study.is_demo is True
    assert study.persona_count == len(personas)
    assert sorted(study.persona_ids or []) == sorted(p.id for p in personas)
    # The workflow view renders Studies.personas_data (no DB fallback) — it
    # must carry exactly the personas the card claims, or Step 5 reads
    # "Synthesized from 0 synthetic personas" against a card promising 1.
    assert len(study.personas_data or []) == study.persona_count
    assert sorted(p["id"] for p in study.personas_data or []) == sorted(study.persona_ids or [])
    # Honesty of the serialized payload: no EvidenceClaims were retrieved for
    # the study, and grounding is the MEASURED share of OBSERVED claims — never
    # a decoration. OBSERVED claims carry the evidence ids they cite.
    assert claim_count == 0
    for entry in study.personas_data or []:
        attrs = entry["attributes"]
        observed = [a for a in attrs if a["provenance_class"] == "OBSERVED"]
        assert entry["grounding_ratio"] == round(len(observed) / len(attrs), 2)
        assert entry["grounding_basis"] == ("citations_verified" if observed else "no_evidence_retrieved")
        assert all(a["evidence"] for a in observed)
        assert all(a["evidence"] is None for a in attrs if a["provenance_class"] != "OBSERVED")
        assert entry["data_source"] == "cached"
        assert entry["country_code"] == "BD"

    # EVERY seeded study's claimed counts must match the rows actually seeded
    # for it — demo_02/03 used to advertise 4+2 personas against 0 rows each.
    for s in all_studies:
        rows = persona_rows_by_study[s.id]
        assert s.persona_count == len(rows), f"{s.id} claims {s.persona_count} personas, seeded {len(rows)}"
        assert sorted(s.persona_ids or []) == sorted(rows), f"{s.id} persona_ids do not match seeded rows"
        assert len(s.personas_data or []) <= s.persona_count

    assert report is not None
    assert report.metrics["total_personas"] == len(personas)
    assert report.metrics["total_interviews"] == interviews

    prose = " ".join(
        [
            study.duration_text or "",
            (study.findings or {}).get("executive_summary", ""),
            report.executive_summary or "",
            *(report.key_findings or []),
            *(report.recommendations or []),
            report.limitations or "",
            *(report.major_risks or []),
        ]
    ).lower()
    if interviews == 0:
        assert "interviewed" not in prose
        assert "were interviewed" not in prose


# ------------------------------------------------------------------------
# Seed coherence & honesty (2026-09-06 rewrite): one BDT-priced student-planner
# business, one Dhaka student persona, real dataset records as the only
# citable evidence, one serializer for both persona views, no seeded provenance.
# ------------------------------------------------------------------------

import json
from pathlib import Path

from bebshax.auth.security import verify_password
from bebshax.db import seed as seed_mod
from bebshax.db.models import LLMRequests, Personas, Studies
from bebshax.persona.orm import PersonaAttributes, PersonaDetails, PersonaEvidence

_JWT = "test_secret_at_least_32_characters_long_12345"
REAL_PROCESSED_DIR = Path(__file__).resolve().parents[4] / "data" / "processed"


def _settings(processed_dir: Path):
    from bebshax.config import Settings

    return Settings(demo_mode=True, jwt_secret=_JWT, processed_dir=str(processed_dir))


# Excerpts of the real cited reviews (data/processed is gitignored, so tests
# carry the text they need; coerce_provenance requires lexical overlap).
_REAL_EXCERPTS = {
    "49f85be0-fb49-5bba-8875-c650a0ae6ba3": (
        "My son started classes last week at the university. He is able to record his "
        "assignments, test schedules, and more. The calendar follows the school year."
    ),
    "c9775182-05c0-54ad-aaca-ec5f1c46cad3": (
        "This is a cute planner. It's a great size for students. There's adequate space for "
        "writing assignments and appointments. It has a weekly view as well as a monthly one."
    ),
    "1e1dc9ca-fd6e-5b1d-b46b-a9cfc24f3753": (
        "I started using Google calendar and became digitized. It has both a weekly view and "
        "monthly. Mine follows the school year."
    ),
    "faa65d00-1be6-5eaf-b10c-538ea790263c": (
        "It's convenient sharing online calendars and being able to access it from my laptop or "
        "my phone. I am still using the digital calendar. The physical planner is more of a fun outlet."
    ),
}


def _corpus_with(tmp_path: Path, refs) -> Path:
    """A processed dir whose amazon jsonl holds exactly ``refs`` (real ids and
    excerpts) plus a decoy record, mimicking data/processed."""
    processed = tmp_path / "processed"
    processed.mkdir(exist_ok=True)
    lines = [json.dumps({"id": "decoy-0000", "text": "Great stapler, very sturdy and reliable."})]
    for ref in refs:
        lines.append(json.dumps({"id": ref.record_id, "text": _REAL_EXCERPTS[ref.record_id]}))
    (processed / "amazon_reviews_office_products.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return processed


async def _load_rows(sm):
    async with sm() as session:
        attrs = list((await session.execute(select(PersonaAttributes).where(PersonaAttributes.persona_id == seed_mod.DEMO_PERSONA_ID))).scalars())
        evidence = list((await session.execute(select(PersonaEvidence).where(PersonaEvidence.persona_id == seed_mod.DEMO_PERSONA_ID))).scalars())
        details = await session.get(PersonaDetails, seed_mod.DEMO_PERSONA_ID)
        study = await session.get(Studies, seed_mod.DEMO_STUDY_ID)
    return attrs, evidence, details, study


@pytest.mark.asyncio
async def test_seed_writes_no_llm_requests_rows(monkeypatch, memory_sessionmaker, tmp_path):
    """The old seed inserted a fabricated provenance row (req_seed_demo_01,
    pollinations/deepseek-r1, 1180 ms). Provenance comes from real calls only."""
    monkeypatch.setattr("bebshax.config.get_settings", lambda: _settings(_corpus_with(tmp_path, seed_mod.DEMO_EVIDENCE_REFS)))
    assert await seed_demo_data(memory_sessionmaker) is True
    async with memory_sessionmaker() as session:
        count = (await session.execute(select(func.count()).select_from(LLMRequests))).scalar()
    assert count == 0
    assert "LLMRequests" not in seed_mod.__dict__  # not even imported


@pytest.mark.asyncio
async def test_personas_data_provenance_matches_persona_attributes(monkeypatch, memory_sessionmaker, tmp_path):
    """Two views, one truth: the workflow payload must carry the same provenance
    class and evidence ids as the persona_attributes rows for every claim."""
    monkeypatch.setattr("bebshax.config.get_settings", lambda: _settings(_corpus_with(tmp_path, seed_mod.DEMO_EVIDENCE_REFS)))
    assert await seed_demo_data(memory_sessionmaker) is True
    attrs, _, _, study = await _load_rows(memory_sessionmaker)
    (payload,) = study.personas_data

    by_value = {a.value: a for a in attrs}
    assert len(payload["attributes"]) == len(attrs) > 0
    for entry in payload["attributes"]:
        value = entry["title"] if entry["description"] == entry["title"] else f"{entry['title']}: {entry['description']}"
        row = by_value[value]
        assert entry["provenance_class"] == row.provenance_class
        assert (entry["evidence"] or []) == list(row.evidence_ids or [])
        assert entry["category"] == row.key
    observed_rows = sum(1 for a in attrs if a.provenance_class == "OBSERVED")
    assert payload["grounding_ratio"] == round(observed_rows / len(attrs), 2) > 0
    assert payload["grounding_basis"] == "citations_verified"
    # the claim_provenance block (what the UI's ProvenanceChip reads) agrees too
    flat = [e for group in payload["detailed_attributes"]["claim_provenance"].values() for e in group]
    assert sorted(e["provenance"] for e in flat) == sorted(a.provenance_class for a in attrs)


@pytest.mark.asyncio
async def test_no_observed_claim_without_evidence_that_exists_in_the_corpus(monkeypatch, memory_sessionmaker, tmp_path):
    """Only two of the four cited records are present: claims resting solely on
    the missing ones must be INFERRED with their citations stripped, and every
    surviving OBSERVED citation must resolve to a stored evidence row AND a
    record in the processed corpus."""
    present = (seed_mod._REV_UNIVERSITY_SON, seed_mod._REV_WEEKLY_MONTHLY)
    processed = _corpus_with(tmp_path, present)
    monkeypatch.setattr("bebshax.config.get_settings", lambda: _settings(processed))
    assert await seed_demo_data(memory_sessionmaker) is True
    attrs, evidence, _, _ = await _load_rows(memory_sessionmaker)

    corpus_ids = {
        json.loads(line)["id"]
        for line in (processed / "amazon_reviews_office_products.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    stored_ids = {e.id for e in evidence}
    assert stored_ids == {r.record_id for r in present}  # only verified records are stored
    observed = [a for a in attrs if a.provenance_class == "OBSERVED"]
    assert observed, "records were present — some claims must be OBSERVED"
    for row in observed:
        assert row.evidence_ids, row.value
        assert set(row.evidence_ids) <= stored_ids <= corpus_ids
    # needs cited (weekly_monthly, digitized): only weekly_monthly exists → OBSERVED, citation trimmed.
    needs = next(a for a in attrs if a.key == "need")
    assert needs.provenance_class == "OBSERVED" and needs.evidence_ids == [seed_mod._REV_WEEKLY_MONTHLY.record_id]
    # technology cited (digital_shared, digitized): neither exists → downgraded, citations stripped.
    tech = next(a for a in attrs if a.key == "technology_usage")
    assert tech.provenance_class == "INFERRED" and tech.evidence_ids == []
    # Every stored evidence text is the corpus record's own text, never hand-written.
    assert all(e.text == _REAL_EXCERPTS[e.id] and e.source == "amazon_reviews_office_products" for e in evidence)


@pytest.mark.asyncio
async def test_seed_without_corpus_downgrades_every_observed_claim_and_warns(monkeypatch, memory_sessionmaker, tmp_path):
    empty = tmp_path / "processed_empty"
    empty.mkdir()
    monkeypatch.setattr("bebshax.config.get_settings", lambda: _settings(empty))
    assert await seed_demo_data(memory_sessionmaker) is True
    attrs, evidence, details, study = await _load_rows(memory_sessionmaker)
    assert evidence == []
    assert all(a.provenance_class != "OBSERVED" and not a.evidence_ids for a in attrs)
    assert any("evidence corpus not present" in w for w in details.warnings)
    (payload,) = study.personas_data
    assert payload["grounding_ratio"] == 0.0 and payload["grounding_basis"] == "no_evidence_retrieved"
    assert "evidence corpus not present" in payload["critic_notes"]


@pytest.mark.asyncio
async def test_seed_refuses_citations_into_non_grounding_corpora(tmp_path):
    """PersonaHub sketches are synthetic by construction — never citable."""
    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "personahub_sample.jsonl").write_text(json.dumps({"id": "ph-1", "persona": "a student who loves planners"}) + "\n", encoding="utf-8")
    found = seed_mod.load_seed_evidence(processed, (seed_mod.SeedEvidenceRef("ph-1", "personahub_sample"),))
    assert found == []


@pytest.mark.skipif(
    not (REAL_PROCESSED_DIR / "amazon_reviews_office_products.jsonl").exists(),
    reason="real processed corpus not present (data/processed is gitignored; run scripts/setup_datasets.py)",
)
def test_every_seed_citation_exists_in_the_real_corpus_with_real_text():
    found = seed_mod.load_seed_evidence(REAL_PROCESSED_DIR)
    assert {e.id for e in found} == {r.record_id for r in seed_mod.DEMO_EVIDENCE_REFS}
    texts = {e.id: e.text for e in found}
    # Spot-check that the cited records say what the claims lean on.
    assert "assignments, test schedules" in texts[seed_mod._REV_UNIVERSITY_SON.record_id]
    assert "weekly view as well as a monthly" in texts[seed_mod._REV_WEEKLY_MONTHLY.record_id]
    assert "laptop or my phone" in texts[seed_mod._REV_DIGITAL_SHARED.record_id]
    assert "Google calendar" in texts[seed_mod._REV_DIGITIZED.record_id]
    profile = seed_mod.build_demo_persona(found)
    observed = [a for a in profile.attributes if a.provenance_class.value == "OBSERVED"]
    assert {a.key for a in observed} == {"need", "behavior", "technology_usage"}


@pytest.mark.asyncio
async def test_showcase_case_is_coherent_and_demo_login_unchanged(monkeypatch, memory_sessionmaker, tmp_path):
    monkeypatch.setattr("bebshax.config.get_settings", lambda: _settings(_corpus_with(tmp_path, seed_mod.DEMO_EVIDENCE_REFS)))
    assert await seed_demo_data(memory_sessionmaker) is True
    async with memory_sessionmaker() as session:
        user = (await session.execute(select(Users).where(Users.email == "founder@bebshax.ai"))).scalars().one()
        business = await session.get(Businesses, seed_mod.DEMO_BUSINESS_ID)
        persona = await session.get(Personas, seed_mod.DEMO_PERSONA_ID)
        details = await session.get(PersonaDetails, seed_mod.DEMO_PERSONA_ID)
        studies = list((await session.execute(select(Studies))).scalars())

    # login fixture unchanged (docs/DEMO.md), user is not a persona
    assert verify_password("Password123!", user.hashed_password)
    assert user.full_name != persona.name and user.id != persona.id
    # business context matches the BDT student-planner studies, persona matches the business
    blob = f"{business.name} {business.description} {business.industry} {business.target_market}".lower()
    assert "student" in blob and "৳" in blob and "dhaka" in blob
    assert "fintech" not in blob and "rideshare" not in blob
    assert "dhaka" in details.location.lower() and "bangladesh" in details.location.lower()
    assert persona.business_id == business.id and persona.data_source == "cached"
    assert persona.generation_model == seed_mod.SEED_GENERATION_MODEL  # no LLM was claimed
    assert all(s.user_id == user.id for s in studies)
    assert all("BDT" in (s.prompt or "") or "student" in (s.prompt or "").lower() or "university" in (s.prompt or "").lower() or "calendar" in (s.prompt or "").lower() for s in studies)


@pytest.mark.asyncio
async def test_seed_is_idempotent(monkeypatch, memory_sessionmaker, tmp_path):
    monkeypatch.setattr("bebshax.config.get_settings", lambda: _settings(_corpus_with(tmp_path, seed_mod.DEMO_EVIDENCE_REFS)))
    assert await seed_demo_data(memory_sessionmaker) is True
    assert await seed_demo_data(memory_sessionmaker) is False
    async with memory_sessionmaker() as session:
        personas = (await session.execute(select(func.count()).select_from(Personas))).scalar()
        businesses = (await session.execute(select(func.count()).select_from(Businesses))).scalar()
    assert personas == 1 and businesses == 1
