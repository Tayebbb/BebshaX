"""Claim extraction honesty rules (research-integrity hardening).

Citations only count when they reference chunks the model was actually shown;
self-declared "supported" without verifiable citations is downgraded; the
deterministic fallback never claims verification it cannot perform.
"""

import json

import pytest

from bebshax.db.models import EvidenceChunks, EvidenceSources
from bebshax.research.claim_extractor import (
    extract_claims_with_llm,
    extract_deterministic_claims,
)


class _StubLLM:
    def __init__(self, text: str) -> None:
        self._text = text
        self.requests: list = []

    async def complete(self, request):
        self.requests.append(request)

        class _R:
            text = self._text

        return _R()


def _source(sid: str, content: str) -> EvidenceSources:
    return EvidenceSources(id=sid, study_id="st1", title=f"src {sid}", content=content, source_type="curated_sample")


def _chunk(cid: str, sid: str, content: str) -> EvidenceChunks:
    return EvidenceChunks(id=cid, source_id=sid, study_id="st1", content=content, embedding=[])


def _fixture():
    sources = [_source("src_1", "users report pricing friction and fragmented workflows")]
    chunks = [_chunk("chk_1", "src_1", "pricing friction is a recurring pain point")]
    return sources, chunks


@pytest.mark.asyncio
async def test_supported_claim_with_fabricated_citations_is_downgraded():
    payload = json.dumps(
        [
            {
                "claim_text": "Users love paying more.",
                "status": "supported",
                "category": "pricing",
                "confidence": 0.9,
                "supporting_source_ids": ["src_fake"],
                "supporting_chunk_ids": ["chk_fake"],
                "rationale": "model says so",
            },
            {"claim_text": "b", "status": "inference", "category": "x", "confidence": 0.4,
             "supporting_source_ids": [], "supporting_chunk_ids": [], "rationale": ""},
            {"claim_text": "c", "status": "unsupported", "category": "x", "confidence": 0.2,
             "supporting_source_ids": [], "supporting_chunk_ids": [], "rationale": ""},
        ]
    )
    sources, chunks = _fixture()
    claims = await extract_claims_with_llm("idea", sources, chunks, _StubLLM(payload))
    first = claims[0]
    assert first["status"] == "inference"  # never trusted without verifiable citations
    assert first["supporting_source_ids"] == []
    assert first["supporting_chunk_ids"] == []
    assert "Downgraded" in first["rationale"]


@pytest.mark.asyncio
async def test_valid_citations_survive_intersection():
    payload = json.dumps(
        [
            {
                "claim_text": "Pricing friction recurs.",
                "status": "supported",
                "category": "pricing",
                "confidence": 0.8,
                "supporting_source_ids": ["src_1", "src_fake"],
                "supporting_chunk_ids": ["chk_1", "chk_fake"],
                "rationale": "cited",
            },
            {"claim_text": "b", "status": "inference", "category": "x", "confidence": 0.4,
             "supporting_source_ids": [], "supporting_chunk_ids": [], "rationale": ""},
            {"claim_text": "c", "status": "unsupported", "category": "x", "confidence": 0.2,
             "supporting_source_ids": [], "supporting_chunk_ids": [], "rationale": ""},
        ]
    )
    sources, chunks = _fixture()
    claims = await extract_claims_with_llm("idea", sources, chunks, _StubLLM(payload))
    first = claims[0]
    assert first["status"] == "supported"
    assert first["supporting_source_ids"] == ["src_1"]  # fabricated id stripped
    assert first["supporting_chunk_ids"] == ["chk_1"]


@pytest.mark.asyncio
async def test_unknown_status_defaults_to_inference_not_supported():
    payload = json.dumps(
        [
            {"claim_text": "a", "status": "verified!!", "category": "x", "confidence": 0.9,
             "supporting_source_ids": ["src_1"], "supporting_chunk_ids": [], "rationale": ""},
            {"claim_text": "b", "status": "inference", "category": "x", "confidence": 0.4,
             "supporting_source_ids": [], "supporting_chunk_ids": [], "rationale": ""},
            {"claim_text": "c", "status": "unsupported", "category": "x", "confidence": 0.2,
             "supporting_source_ids": [], "supporting_chunk_ids": [], "rationale": ""},
        ]
    )
    sources, chunks = _fixture()
    claims = await extract_claims_with_llm("idea", sources, chunks, _StubLLM(payload))
    assert claims[0]["status"] == "inference"


def test_deterministic_fallback_never_claims_supported():
    sources, chunks = _fixture()
    claims = extract_deterministic_claims("idea", sources, chunks)
    assert claims, "fallback must produce hypothesis claims"
    for c in claims:
        assert c["status"] in ("inference", "unsupported")
        assert c["confidence"] <= 0.5
