"""Copilot persona grounding must be measured, not asserted.

/api/study/generate-personas is the endpoint the main 5-step workflow calls.
It used to hard-code grounding_ratio = 0.0 for every persona while retrieving
no evidence at all, so the UI rendered "0% Grounded" as if that were a
measurement. Grounding is now computed from verified citations, and the
response always says which basis the number came from.
"""

import json
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.db.models import Base, EvidenceClaims, Studies
from bebshax.main import app


class _CitingRouter:
    """Returns one persona citing the first claim alias shown in the prompt."""

    def __init__(self, cite: str | None) -> None:
        self.cite = cite
        self.prompts: list[str] = []

    async def complete(self, request):
        self.prompts.append(request.messages[-1].content)
        persona = {
            "name": "Rafiul Karim",
            "attributes": [
                {
                    "category": "Goals",
                    "title": "Cut weekly grocery spend",
                    "provenance_class": "OBSERVED",
                    "evidence": [self.cite] if self.cite else None,
                },
                {
                    "category": "Needs",
                    "title": "Same-day delivery",
                    "provenance_class": "OBSERVED",
                    "evidence": ["C99"],  # never shown → must be stripped
                },
            ],
        }
        return SimpleNamespace(
            text=json.dumps([persona]), provider="fake", model="m1"
        )


async def _app_with_study(study_id: str, claim_texts: list[str]):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_sessionmaker = session_maker

    async with session_maker() as session:
        session.add(
            Studies(id=study_id, user_id="usr_default", title="Grounding Study", status="draft")
        )
        for i, text in enumerate(claim_texts):
            session.add(
                EvidenceClaims(
                    id=f"clm_ground_{i}",
                    study_id=study_id,
                    claim_text=text,
                    category="general",
                    confidence=0.9,
                )
            )
        await session.commit()
    return session_maker


_ROLES = [
    {
        "id": "role_primary",
        "role": "PRIMARY USER",
        "description": "Core target user",
        "count": 1,
        "selected": True,
    }
]


@pytest.mark.asyncio
async def test_zero_grounding_without_evidence_is_labeled_as_an_absence():
    await _app_with_study("std_ground_none", [])
    app.state.llm_router = None  # skeleton path

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/study/generate-personas",
            json={"study_id": "std_ground_none", "study_prompt": "grocery app", "roles": _ROLES},
        )

    assert res.status_code == 200
    personas = res.json()
    assert personas
    for p in personas:
        assert p["grounding_ratio"] == 0.0
        # The marker is what stops the UI implying a measured zero.
        assert p["grounding_basis"] == "no_evidence_retrieved"
        assert p["evidence_claim_count"] == 0


@pytest.mark.asyncio
async def test_grounding_is_computed_from_verified_citations_only():
    await _app_with_study(
        "std_ground_some", ["Shoppers abandon carts over delivery fees.", "Weekly budgets are tight."]
    )
    router = _CitingRouter(cite="C1")
    app.state.llm_router = router

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/study/generate-personas",
            json={"study_id": "std_ground_some", "study_prompt": "grocery app", "roles": _ROLES},
        )

    assert res.status_code == 200
    assert "C1: Shoppers abandon carts" in router.prompts[0], "claims must be shown to the model"

    persona = res.json()[0]
    assert persona["grounding_basis"] == "citations_verified"
    assert persona["evidence_claim_count"] == 2
    # 1 of 2 attributes cited a claim we actually showed.
    assert persona["grounding_ratio"] == 0.5

    cited, fabricated = persona["attributes"][0], persona["attributes"][1]
    assert cited["provenance_class"] == "OBSERVED"
    assert cited["evidence"] == ["clm_ground_0"], "aliases resolve to real claim ids"
    # An unshown id is not verifiable → stripped and downgraded, never upgraded.
    assert fabricated["provenance_class"] == "INFERRED"
    assert fabricated["evidence"] is None


@pytest.mark.asyncio
async def test_uncited_llm_personas_score_zero_even_with_evidence_present():
    await _app_with_study("std_ground_uncited", ["A claim the model ignores."])
    app.state.llm_router = _CitingRouter(cite=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/study/generate-personas",
            json={"study_id": "std_ground_uncited", "study_prompt": "grocery app", "roles": _ROLES},
        )

    persona = res.json()[0]
    assert persona["grounding_ratio"] == 0.0, "self-declared OBSERVED must never count"
    assert persona["grounding_basis"] == "citations_verified"
    assert all(a["provenance_class"] == "INFERRED" for a in persona["attributes"])
