"""Research-layer honesty (GROUP P): claim confidence derives from verifiable
citations, contested evidence is a first-class status, and the planner cannot be
broken out of by quotes in the business idea."""

import json

from bebshax.db.models import EvidenceChunks, EvidenceSources
from bebshax.llm.prompt_safety import UNTRUSTED_RULE
from bebshax.research.claim_extractor import citation_confidence, extract_claims_with_llm
from bebshax.research.planner import generate_structured_research_plan


class _StubLLM:
    def __init__(self, text: str) -> None:
        self._text = text
        self.requests: list = []

    async def complete(self, request):
        self.requests.append(request)

        class _Result:
            text = self._text
            provider = "fake"
            model = "stub"

        return _Result()


def _source(sid: str, content: str) -> EvidenceSources:
    return EvidenceSources(id=sid, study_id="st1", title=f"src {sid}", content=content, source_type="curated_sample")


def _chunk(cid: str, sid: str, content: str) -> EvidenceChunks:
    return EvidenceChunks(id=cid, source_id=sid, study_id="st1", content=content, embedding=[])


def _fixture():
    sources = [
        _source("src_1", "students pay under 300 taka for lunch"),
        _source("src_2", "students pay about 1,200 taka for lunch"),
    ]
    chunks = [
        _chunk("chk_1", "src_1", "under 300 taka for lunch"),
        _chunk("chk_1b", "src_1", "another chunk from the same source"),
        _chunk("chk_2", "src_2", "about 1,200 taka for lunch"),
    ]
    return sources, chunks


def _claim(**overrides) -> dict:
    base = {
        "claim_text": "Lunch spend is low.",
        "status": "supported",
        "category": "pricing",
        "confidence": 0.99,
        "supporting_source_ids": [],
        "supporting_chunk_ids": [],
        "rationale": "",
    }
    base.update(overrides)
    return base


_FILLERS = [
    _claim(claim_text="b", status="inference", confidence=0.4),
    _claim(claim_text="c", status="unsupported", confidence=0.2),
]


def test_persona_hardening_citation_confidence_table() -> None:
    assert citation_confidence(0) == 0.0
    assert citation_confidence(1) == 0.5
    assert citation_confidence(2) == 0.8
    assert citation_confidence(7) == 0.8


async def test_persona_hardening_confidence_ignores_model_self_score() -> None:
    sources, chunks = _fixture()
    payload = json.dumps(
        [
            _claim(claim_text="zero", status="inference"),  # 0.99 self-score, no citations
            _claim(claim_text="one", supporting_source_ids=["src_1"], supporting_chunk_ids=["chk_1", "chk_1b"]),
            _claim(claim_text="two", supporting_source_ids=["src_1"], supporting_chunk_ids=["chk_2"]),
        ]
    )
    claims = await extract_claims_with_llm("idea", sources, chunks, _StubLLM(payload))
    by_text = {c["claim_text"]: c for c in claims}
    assert by_text["zero"]["confidence"] == 0.0
    # two chunks of ONE source are one independent source
    assert by_text["one"]["confidence"] == 0.5
    # a source cited directly plus a chunk from a different source → two sources
    assert by_text["two"]["confidence"] == 0.8


async def test_persona_hardening_conflicts_with_makes_a_claim_contested() -> None:
    sources, chunks = _fixture()
    payload = json.dumps(
        [
            _claim(
                claim_text="Students pay under 300 taka.",
                supporting_source_ids=["src_1"],
                supporting_chunk_ids=["chk_1"],
                conflicts_with=["src_2", "src_ghost"],
            ),
            _claim(claim_text="explicit", status="contested", supporting_source_ids=["src_1"], conflicts_with=["src_2"]),
            *_FILLERS,
        ]
    )
    claims = await extract_claims_with_llm("idea", sources, chunks, _StubLLM(payload))
    first, explicit = claims[0], claims[1]
    assert first["status"] == "contested"
    assert first["contradicting_source_ids"] == ["src_2"]  # ghost id stripped
    assert "Contested" in first["rationale"]
    assert explicit["status"] == "contested"
    assert explicit["contradicting_source_ids"] == ["src_2"]


async def test_persona_hardening_extraction_schema_requests_conflicts() -> None:
    sources, chunks = _fixture()
    stub = _StubLLM(json.dumps(_FILLERS + [_claim(claim_text="x", status="inference")]))
    await extract_claims_with_llm("idea", sources, chunks, stub)
    system_prompt = stub.requests[0].messages[0].content
    assert "conflicts_with" in system_prompt
    assert "contested" in system_prompt
    assert "confidence (float" not in system_prompt  # the model is no longer asked to self-score


async def test_persona_hardening_scalar_citation_fields_do_not_crash() -> None:
    sources, chunks = _fixture()
    payload = json.dumps(
        [_claim(claim_text="x", supporting_source_ids="src_1", supporting_chunk_ids=None, conflicts_with="src_2")]
        + _FILLERS
    )
    claims = await extract_claims_with_llm("idea", sources, chunks, _StubLLM(payload))
    assert claims[0]["supporting_source_ids"] == ["src_1"]
    assert claims[0]["status"] == "contested"


# --- planner --------------------------------------------------------------------


async def test_persona_hardening_planner_json_encodes_the_idea() -> None:
    idea = 'A "premium" meal-kit; \\ escape test'
    plan_json = json.dumps(
        {
            "business_idea": idea,
            "target_market": ["students"],
            "problem_areas": ["cost"],
            "behavioral_questions": ["q"],
            "economic_questions": ["q"],
            "competition_questions": ["q"],
            "market_questions": ["q"],
            "dataset_requirements": [
                {
                    "category": "demographics",
                    "description": "why",
                    "target_variables": ["age"],
                    "geographic_scope": "Bangladesh",
                    "population_scope": "students",
                }
            ],
            "summary": "s",
        }
    )
    stub = _StubLLM(plan_json)
    result = await generate_structured_research_plan(idea, llm_service=stub)
    assert result.business_idea == idea

    prompt = stub.requests[0].messages[0].content
    assert f'"business_idea": {json.dumps(idea, ensure_ascii=False)},' in prompt
    assert f'"business_idea": "{idea}"' not in prompt  # raw quotes would break out of the string
    assert UNTRUSTED_RULE in prompt
    assert "<UNTRUSTED_RESEARCH_BRIEF" in prompt and idea in prompt
