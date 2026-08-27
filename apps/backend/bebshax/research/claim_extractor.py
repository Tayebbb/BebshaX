"""Structured claim extraction and empirical evidence classification.

Extracts evidence-supported claims, model inferences, and unsupported assumptions
with complete provenance links and confidence metrics.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Optional

from bebshax.db.models import EvidenceChunks, EvidenceSources
from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType

logger = logging.getLogger(__name__)


def extract_deterministic_claims(
    idea: str,
    sources: list[EvidenceSources],
    chunks: list[EvidenceChunks],
) -> list[dict[str, Any]]:
    """Heuristic fallback claims when the LLM path is unavailable.

    Every claim is a keyword-matched HYPOTHESIS (status "inference", confidence
    ≤ 0.5) — a deterministic matcher cannot verify anything, so it never emits
    "supported". The one "unsupported" entry demonstrates the assumption class.
    """
    claims: list[dict[str, Any]] = []

    def _matching(words: tuple[str, ...]) -> tuple[list[str], list[str]]:
        s_ids = [s.id for s in sources if any(w in s.content.lower() for w in words)]
        c_ids = [c.id for c in chunks if any(w in c.content.lower() for w in words)]
        return s_ids[:3], c_ids[:4]

    rationale = (
        "Heuristic keyword match against curated sample sources — treat as a "
        "hypothesis to verify, not a finding."
    )

    problem_sources, problem_chunks = _matching(("pain", "problem", "fragmented", "struggle", "missed"))
    if problem_sources:
        claims.append({
            "id": f"claim_{uuid.uuid4().hex[:12]}",
            "claim_text": "Matched sample sources describe workflow fragmentation and friction relevant to this idea.",
            "status": "inference",
            "category": "problem",
            "confidence": 0.5,
            "supporting_source_ids": problem_sources,
            "supporting_chunk_ids": problem_chunks,
            "contradicting_source_ids": [],
            "rationale": rationale,
        })

    pricing_sources, pricing_chunks = _matching(("pricing", "subscription", "cost", "affordability", "willingness"))
    if pricing_sources:
        claims.append({
            "id": f"claim_{uuid.uuid4().hex[:12]}",
            "claim_text": "Sampled discussions suggest price sensitivity clusters at low monthly price points.",
            "status": "inference",
            "category": "pricing",
            "confidence": 0.45,
            "supporting_source_ids": pricing_sources,
            "supporting_chunk_ids": pricing_chunks,
            "contradicting_source_ids": [],
            "rationale": rationale,
        })
    else:
        claims.append({
            "id": f"claim_{uuid.uuid4().hex[:12]}",
            "claim_text": "Users will maintain continuous subscriptions without recurring payment friction.",
            "status": "inference",
            "category": "pricing",
            "confidence": 0.4,
            "supporting_source_ids": [],
            "supporting_chunk_ids": [],
            "contradicting_source_ids": [],
            "rationale": "Inferred from general SaaS behavior; no matched sample evidence.",
        })

    comp_sources, comp_chunks = _matching(("complaints", "reviews", "retention", "competitor", "alternatives"))
    if comp_sources:
        claims.append({
            "id": f"claim_{uuid.uuid4().hex[:12]}",
            "claim_text": "Sampled reviews of comparable tools report retention drop-off complaints.",
            "status": "inference",
            "category": "complaints",
            "confidence": 0.45,
            "supporting_source_ids": comp_sources,
            "supporting_chunk_ids": comp_chunks,
            "contradicting_source_ids": [],
            "rationale": rationale,
        })

    behavior_sources, behavior_chunks = _matching(("peer", "collaborative", "routine", "group", "habits"))
    claims.append({
        "id": f"claim_{uuid.uuid4().hex[:12]}",
        "claim_text": "Collaborative features may drive higher retention than solo planning.",
        "status": "inference",
        "category": "behavior",
        "confidence": 0.4 if behavior_sources else 0.3,
        "supporting_source_ids": behavior_sources,
        "supporting_chunk_ids": behavior_chunks,
        "contradicting_source_ids": [],
        "rationale": rationale if behavior_sources else "General product heuristic; no matched sample evidence.",
    })

    # Explicit unsupported-assumption example (never silently promoted).
    claims.append({
        "id": f"claim_{uuid.uuid4().hex[:12]}",
        "claim_text": "Users will sustain premium pricing without subsidies or validation.",
        "status": "unsupported",
        "category": "pricing",
        "confidence": 0.18,
        "supporting_source_ids": [],
        "supporting_chunk_ids": [],
        "contradicting_source_ids": pricing_sources[:2],
        "rationale": "Unverified assumption from the product idea; sampled price-sensitivity signals point the other way.",
    })

    return claims


async def extract_claims_with_llm(
    idea: str,
    sources: list[EvidenceSources],
    chunks: list[EvidenceChunks],
    llm_service: LLMService,
) -> list[dict[str, Any]]:
    """Extract claims and classify evidence status using LLMService."""
    if not chunks or not sources:
        return extract_deterministic_claims(idea, sources, chunks)

    # Format relevant chunks with IDs
    chunk_context = "\n\n".join([
        f"--- CHUNK ID: {c.id} (Source ID: {c.source_id}) ---\n{c.content}"
        for c in chunks[:12]
    ])

    system_prompt = (
        "You are an evidence extraction and empirical claim classification engine for BebshaX.\n"
        "Analyze the provided research chunks for the given product idea.\n"
        "Extract 4 to 6 structured claims across Problem, Competition, Pricing, Behavior, and Complaints.\n\n"
        "CLASSIFICATION RULES:\n"
        "- 'supported' (GREEN): Directly proven by the provided chunk text. Must cite supporting chunk IDs and source IDs.\n"
        "- 'inference' (AMBER): Plausible extrapolation from evidence, but lacks direct confirmation.\n"
        "- 'unsupported' (RED): An unverified assumption from the product idea or contradicted by the evidence.\n\n"
        "NEVER silently promote unsupported information to 'supported'.\n"
        "Output ONLY a valid JSON array of objects with keys: "
        "claim_text, status (supported|inference|unsupported), category, confidence (float 0.1 to 1.0), "
        "supporting_source_ids (list of strings), supporting_chunk_ids (list of strings), rationale."
    )

    user_prompt = f"Product Idea: {idea}\n\nEVIDENCE CHUNKS:\n{chunk_context}"

    request = LLMRequest(
        task=TaskType.EVIDENCE_EXTRACTION,
        messages=[
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ],
        json_mode=True,
        temperature=0.1,
        max_output_tokens=800,
    )

    try:
        result = await llm_service.complete(request)
        text = result.text.strip()
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list) and len(parsed) >= 3:
                # Citations only count when they reference material the model
                # was actually shown — mirrors persona coerce_provenance.
                shown_chunks = chunks[:12]
                valid_chunk_ids = {c.id for c in shown_chunks}
                valid_source_ids = {c.source_id for c in shown_chunks} | {s.id for s in sources}
                extracted = []
                for item in parsed:
                    if not isinstance(item, dict) or not item.get("claim_text"):
                        continue
                    cited_sources = [
                        sid for sid in item.get("supporting_source_ids", []) if sid in valid_source_ids
                    ]
                    cited_chunks = [
                        cid for cid in item.get("supporting_chunk_ids", []) if cid in valid_chunk_ids
                    ]
                    status = str(item.get("status", "")).lower()
                    if status not in ("supported", "inference", "unsupported"):
                        status = "inference"
                    rationale = str(item.get("rationale", "")).strip()
                    if status == "supported" and not (cited_sources or cited_chunks):
                        # Self-declared support with no verifiable citation is
                        # downgraded, never trusted.
                        status = "inference"
                        rationale = (rationale + " [Downgraded: cited evidence ids did not match shown chunks.]").strip()

                    extracted.append({
                        "id": f"claim_{uuid.uuid4().hex[:12]}",
                        "claim_text": str(item["claim_text"]).strip(),
                        "status": status,
                        "category": str(item.get("category", "general")).lower(),
                        "confidence": float(item.get("confidence", 0.5)),
                        "supporting_source_ids": cited_sources,
                        "supporting_chunk_ids": cited_chunks,
                        "contradicting_source_ids": [
                            sid for sid in item.get("contradicting_source_ids", []) if sid in valid_source_ids
                        ],
                        "rationale": rationale,
                    })
                if extracted:
                    return extracted
    except Exception:
        logger.warning(
            "LLM claim extraction failed — falling back to deterministic hypothesis claims",
            exc_info=True,
        )

    return extract_deterministic_claims(idea, sources, chunks)
