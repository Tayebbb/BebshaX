"""Persona test fixtures: sqlite engine with persona tables + fixture datasets."""

import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import bebshax.persona.orm  # noqa: F401 — register persona tables on Base.metadata
from bebshax.db.models import Base
from bebshax.persona.evidence import EvidenceStore


@pytest_asyncio.fixture
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    maker = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest.fixture
def evidence_store(tmp_path) -> EvidenceStore:
    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "personahub_sample.jsonl").write_text(
        "\n".join(
            json.dumps({"persona": p})
            for p in [
                "A budget-conscious university student in Dhaka who orders food online weekly.",
                "A retired school teacher exploring organic groceries in small towns.",
                "A startup founder in Berlin optimizing delivery logistics software.",
            ]
        ),
        encoding="utf-8",
    )
    (processed / "amazon_reviews_office_products.jsonl").write_text(
        json.dumps(
            {"text": "The food delivery arrived late twice and the packaging leaked everywhere."}
        ),
        encoding="utf-8",
    )
    return EvidenceStore(processed)


@pytest.fixture
def persona_json():
    """Factory fixture: builds schema-valid GeneratedPersona JSON payloads."""
    return make_persona_json


def make_persona_json(**overrides) -> str:
    """A schema-valid GeneratedPersona JSON payload for scripted fakes."""
    data = {
        "name": "Rina Akter",
        "age": 24,
        "occupation": "university student",
        "location": "Dhaka, Bangladesh",
        "income_range": "student stipend",
        "education": "BSc in progress",
        "description": (
            "A busy student who orders dinner online most weeknights and compares "
            "prices carefully before checkout."
        ),
        "goals": [
            {"value": "find affordable meal deals", "provenance": "INFERRED", "evidence_ids": []},
            {"value": "save time on weeknights", "provenance": "SYNTHETIC", "evidence_ids": []},
        ],
        "pain_points": [
            {"value": "late deliveries", "provenance": "OBSERVED", "evidence_ids": ["bogus-id"]},
            {"value": "unclear delivery fees", "provenance": "SYNTHETIC", "evidence_ids": []},
        ],
        "needs": [
            {"value": "reliable delivery times", "provenance": "INFERRED", "evidence_ids": []}
        ],
        "motivations": [{"value": "convenience", "provenance": "SYNTHETIC", "evidence_ids": []}],
        "behaviors": [
            {"value": "orders food online weekly", "provenance": "INFERRED", "evidence_ids": []}
        ],
        "technology_usage": [
            {"value": "smartphone-first", "provenance": "SYNTHETIC", "evidence_ids": []}
        ],
        "purchase_behavior": [
            {"value": "compares prices before ordering", "provenance": "INFERRED", "evidence_ids": []}
        ],
        "personality_traits": [
            {"value": "pragmatic", "provenance": "SYNTHETIC", "evidence_ids": []}
        ],
    }
    data.update(overrides)
    return json.dumps(data)
