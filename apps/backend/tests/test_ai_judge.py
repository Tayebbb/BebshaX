"""AI judge: an independent CRITIC pass over a study's artefacts.

The judge only scores and explains; it never writes artefacts and has no
template verdict (no LLM / unusable reply -> explicit failure).
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base, EvidenceClaims, Personas, Studies
from bebshax.evaluation.ai_judge import JUDGE_NOTHING_TO_REVIEW, JUDGE_UNAVAILABLE, RUBRIC, judge_persona, judge_study
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.router import PoolRouter
from bebshax.llm.types import TaskType
from bebshax.main import app
from bebshax.utils.explicit_failures import InsufficientInput, LLMUnavailable, UnusableModelOutput

_VERDICT = {
    "overall_score": 71,
    "dimension_scores": {"grounding": 65, "specificity": 80, "consistency": 74, "honesty": 70, "actionability": 66, "bogus": 99},
    "strengths": ["Personas name the study's actual audience and currency."],
    "issues": [
        {"severity": "high", "artifact": "persona:per_1", "detail": "Budget of 900 has no supporting evidence claim."},
        "Report limitations section is thin.",
    ],
    "verdict": "Specific to the brief but under-evidenced; interviews are missing.",
}


class _StubLLM:
    def __init__(self, *texts: str) -> None:
        self._texts = list(texts)
        self.requests: list = []

    async def complete(self, request):
        self.requests.append(request)
        text = self._texts.pop(0) if len(self._texts) > 1 else self._texts[0]

        class _R:
            provider = "fake"
            model = "critic-1"

        r = _R()
        r.text = text
        return r


async def _seed(session_maker, *, with_persona: bool = True):
    async with session_maker() as session:
        session.add(Users(id="usr_j", email="j@example.com", full_name="J", hashed_password="pw"))
        study = Studies(id="std_j", user_id="usr_j", title="Café POS", prompt="POS software for Lisbon cafés", target_audience="independent café owners", pricing_hypothesis="29 EUR/month", status="in_progress")
        session.add(study)
        if with_persona:
            session.add(Personas(id="per_1", study_id="std_j", user_id="usr_j", owner_id="usr_j", name="Inês", archetype="Owner-operator", bio="Runs a 12-seat café.", commercial_profile={"monthly_budget": 900, "currency": "EUR"}, generation_model="fake/x"))
            session.add(EvidenceClaims(id="clm_1", study_id="std_j", user_id="usr_j", claim_text="Card payments dominate small cafés in Lisbon", status="supported", category="behavior", confidence=0.5))
        await session.commit()
        return await session.get(Studies, "std_j")


async def _maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_judge_study_scores_against_the_rubric_with_provenance():
    maker = await _maker()
    study = await _seed(maker)
    stub = _StubLLM(json.dumps(_VERDICT))
    async with maker() as session:
        verdict = await judge_study(session, study, stub)

    assert verdict.scope == "study" and verdict.overall_score == 71
    assert set(verdict.dimension_scores) == set(RUBRIC)  # unknown dimensions dropped
    assert verdict.dimension_scores["specificity"] == 80
    assert verdict.issues[0].severity == "high" and verdict.issues[0].artifact == "persona:per_1"
    assert verdict.issues[1].detail.startswith("Report limitations")
    assert verdict.served_by == "fake/critic-1" and verdict.llm_request_id and verdict.attempts == 1
    assert verdict.reviewed_artifacts == {"personas": 1, "segments": 0, "evidence_claims": 1, "interviews": 0, "reports": 0}
    # Routed as CRITIC; the material travels as untrusted data and carries the actual rows.
    req = stub.requests[0]
    assert req.task == TaskType.CRITIC
    body = req.messages[-1].content
    assert "MATERIAL_UNDER_REVIEW" in body and "Inês" in body and "Card payments dominate" in body
    assert "grounding" in req.messages[0].content and "Do not rewrite" in req.messages[0].content


@pytest.mark.asyncio
async def test_judge_persona_reviews_one_persona_only():
    maker = await _maker()
    study = await _seed(maker)
    stub = _StubLLM(json.dumps({**_VERDICT, "overall_score": 55}))
    async with maker() as session:
        persona = await session.get(Personas, "per_1")
        verdict = await judge_persona(session, study, persona, stub)
    assert verdict.scope == "persona" and verdict.overall_score == 55
    assert verdict.reviewed_artifacts == {"personas": 1}
    assert "ONE synthetic persona" in stub.requests[0].messages[0].content


@pytest.mark.asyncio
async def test_judge_fails_explicitly_without_llm_or_material_or_usable_reply():
    maker = await _maker()
    study = await _seed(maker, with_persona=False)
    async with maker() as session:
        with pytest.raises(LLMUnavailable):
            await judge_study(session, study, None)
        with pytest.raises(InsufficientInput) as info:
            await judge_study(session, study, _StubLLM("{}"))
        assert info.value.error_code == JUDGE_NOTHING_TO_REVIEW

    maker2 = await _maker()
    study2 = await _seed(maker2)
    stub = _StubLLM("no json", "still nothing")
    async with maker2() as session:
        with pytest.raises(UnusableModelOutput) as info:
            await judge_study(session, study2, stub)
    assert info.value.error_code == JUDGE_UNAVAILABLE and len(stub.requests) == 2


@pytest.mark.asyncio
async def test_verdict_without_a_numeric_overall_score_is_unusable_never_zero():
    """Observed live: a 3B route answered with a generic verdict and no usable
    score; a default of 0 turned that into an all-zero review the model never
    gave. Missing or non-numeric overall_score -> retry -> judge_unavailable."""
    maker = await _maker()
    study = await _seed(maker)
    missing = {k: v for k, v in _VERDICT.items() if k != "overall_score"}
    stub = _StubLLM(json.dumps(missing), json.dumps({**_VERDICT, "overall_score": "n/a"}))
    async with maker() as session:
        with pytest.raises(UnusableModelOutput) as info:
            await judge_study(session, study, stub)
    assert info.value.error_code == JUDGE_UNAVAILABLE
    assert info.value.attempts == 2 and len(stub.requests) == 2
    assert "no verdict was invented" in info.value.detail


@pytest.mark.asyncio
async def test_non_numeric_dimensions_are_omitted_not_zeroed():
    maker = await _maker()
    study = await _seed(maker)
    reply = {
        **_VERDICT,
        "overall_score": "71",  # numeric strings are numbers
        "dimension_scores": {"grounding": "n/a", "specificity": "80", "consistency": None, "honesty": 70.4, "actionability": True, "bogus": 50},
    }
    stub = _StubLLM(json.dumps(reply))
    async with maker() as session:
        verdict = await judge_study(session, study, stub)
    assert verdict.overall_score == 71
    assert verdict.dimension_scores == {"specificity": 80, "honesty": 70}  # absence, not 0
    assert "grounding" not in verdict.dimension_scores


@pytest.mark.asyncio
async def test_an_unfilled_schema_slot_artifact_is_blanked_but_the_detail_is_kept():
    maker = await _maker()
    study = await _seed(maker)
    reply = {
        **_VERDICT,
        "issues": [
            {"severity": "high", "artifact": "persona:<id>", "detail": "Budget of 900 has no supporting evidence claim."},
            {"severity": "low", "artifact": "persona:<id>|report|interview:<id>|segment:<id>|evidence", "detail": "Limitations are thin."},
            {"severity": "medium", "artifact": "persona:per_1", "detail": "Occupation contradicts the bio."},
        ],
    }
    stub = _StubLLM(json.dumps(reply))
    async with maker() as session:
        verdict = await judge_study(session, study, stub)
    assert [i.artifact for i in verdict.issues] == ["", "", "persona:per_1"]
    assert verdict.issues[0].detail.startswith("Budget of 900") and verdict.issues[1].detail == "Limitations are thin."
    assert "<id>" not in verdict.model_dump_json()


@pytest.mark.asyncio
async def test_ai_review_endpoints_gate_and_envelope():
    maker = await _maker()
    await _seed(maker)
    app.state.db_sessionmaker = maker
    fake = FakeAdapter(routes=[FakeRoute(candidate=RouteCandidate(provider="pollinations", model="deepseek-r1"), reply=json.dumps(_VERDICT))])
    app.state.llm_service = PoolRouter({n: fake for n in ("openrouter", "freellmpool", "ollama", "pollinations")})

    owner = {"Authorization": f"Bearer {create_access_token({'sub': 'usr_j', 'email': 'j@example.com'})}"}
    async with maker() as session:
        session.add(Users(id="usr_x", email="x@example.com", full_name="X", hashed_password="pw"))
        await session.commit()
    intruder = {"Authorization": f"Bearer {create_access_token({'sub': 'usr_x', 'email': 'x@example.com'})}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        rubric = await client.get("/api/ai-review/rubric")
        assert rubric.status_code == 200 and set(rubric.json()["dimensions"]) == set(RUBRIC)

        assert (await client.post("/api/studies/std_j/ai-review", headers=intruder)).status_code == 404
        assert (await client.post("/api/studies/std_j/ai-review")).status_code in (401, 403, 404)

        res = await client.post("/api/studies/std_j/ai-review", headers=owner)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["study_id"] == "std_j" and body["overall_score"] == 71
        assert body["served_by"] == "pollinations/deepseek-r1"

        res_p = await client.post("/api/studies/std_j/personas/per_1/ai-review", headers=owner)
        assert res_p.status_code == 200 and res_p.json()["persona_id"] == "per_1"
        assert (await client.post("/api/studies/std_j/personas/per_nope/ai-review", headers=owner)).status_code == 404

        app.state.llm_service = None
        res_none = await client.post("/api/studies/std_j/ai-review", headers=owner)
        assert res_none.status_code == 503 and res_none.json()["error_code"] == "llm_unavailable"
    app.state.llm_service = None
