"""Structured claim extraction and empirical evidence classification.

Claims are written by the model from THIS study's evidence chunks and
verified deterministically (citations must point at shown material;
confidence derives from independent sources). There is no canned claim list:
no evidence → no claims; unusable model output → explicit failure.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from bebshax.db.models import EvidenceChunks, EvidenceSources
from bebshax.llm.json_utils import parse_llm_json, unwrap_list
from bebshax.llm.prompt_safety import UNTRUSTED_RULE, untrusted_block
from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.research.search_provider import lexical_relevance
from bebshax.utils.explicit_failures import UnusableModelOutput

logger = logging.getLogger(__name__)

CLAIM_STATUSES = ("supported", "inference", "unsupported", "contested")


def citation_confidence(distinct_sources: int) -> float:
    """Confidence is a function of verifiable citations, never the model's
    self-score: 0 sources → 0.0, 1 → 0.5, ≥2 independent sources → 0.8."""
    if distinct_sources <= 0:
        return 0.0
    if distinct_sources == 1:
        return 0.5
    return 0.8


def _as_list(value: Any) -> list[Any]:
    """Model output is untrusted: a missing/scalar field must not crash the parser."""
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


CLAIMS_EXTRACTION_UNPARSEABLE = "claims_extraction_failed"
_MAX_CHUNKS_SHOWN = 12
_MAX_ATTEMPTS = 2


def rank_chunks_for_idea(idea: str, chunks: list[EvidenceChunks], limit: int = _MAX_CHUNKS_SHOWN) -> list[EvidenceChunks]:
    """Chunks most lexically related to the idea first (never insertion order),
    so the model sees the most relevant material within the prompt budget."""
    scored = [(lexical_relevance(idea, c.content or ""), i, c) for i, c in enumerate(chunks)]
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [c for _, _, c in scored[:limit]]


async def extract_claims_with_llm(
    idea: str,
    sources: list[EvidenceSources],
    chunks: list[EvidenceChunks],
    llm_service: LLMService,
) -> list[dict[str, Any]]:
    """Extract and classify claims from THIS study's evidence chunks.

    - No chunks → ``[]`` (the run records ``claims_status="no_evidence"``);
      there is no canned hypothesis list.
    - Unusable model reply → one retry with the same request, then
      ``UnusableModelOutput`` so the run step fails explicitly.
    - ``LLMError`` propagates (infrastructure is never masked).
    Verification is deterministic: "supported" only with a citation to a shown
    chunk/source; confidence derives from the number of distinct cited sources.
    """
    if not chunks or not sources:
        return []

    shown_chunks = rank_chunks_for_idea(idea, chunks)
    chunk_context = "\n\n".join(
        f"--- CHUNK ID: {c.id} (Source ID: {c.source_id}) ---\n{c.content}" for c in shown_chunks
    )

    system_prompt = (
        "You are an evidence extraction and empirical claim classification engine for BebshaX.\n"
        "Analyze the provided research chunks for the given product idea.\n"
        "Extract 3 to 6 structured claims across Problem, Competition, Pricing, Behavior, and Complaints — "
        "only claims that the chunks actually speak to; do not pad with generic statements.\n\n"
        "CLASSIFICATION RULES:\n"
        "- 'supported' (GREEN): Directly proven by the provided chunk text. Must cite supporting chunk IDs and source IDs.\n"
        "- 'inference' (AMBER): Plausible extrapolation from evidence, but lacks direct confirmation.\n"
        "- 'contested' (AMBER): The provided chunks DISAGREE with each other on this point — list the disagreeing "
        "source IDs in conflicts_with.\n"
        "- 'unsupported' (RED): An unverified assumption from the product idea or contradicted by the evidence.\n\n"
        "NEVER silently promote unsupported information to 'supported'. Whenever two chunks contradict each other "
        "on a claim, report both sides via conflicts_with instead of picking one.\n"
        "Output ONLY a valid JSON object with one key \"claims\" holding an array of objects with keys: "
        "claim_text, status (supported|inference|contested|unsupported), category, "
        "supporting_source_ids (list of strings), supporting_chunk_ids (list of strings), "
        "conflicts_with (list of source ids whose text disagrees with the claim), rationale.\n"
        + UNTRUSTED_RULE
    )
    user_prompt = (
        untrusted_block("PRODUCT_IDEA", idea, source="study.prompt")
        + "\n\n"
        + untrusted_block("EVIDENCE_CHUNKS", chunk_context, source="evidence_chunks")
    )
    request = LLMRequest(
        task=TaskType.EVIDENCE_EXTRACTION,
        messages=[
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ],
        json_mode=True,
        temperature=0.1,
        max_output_tokens=900,
    )

    valid_chunk_ids = {c.id for c in shown_chunks}
    chunk_source = {c.id: c.source_id for c in shown_chunks}
    valid_source_ids = {c.source_id for c in shown_chunks} | {s.id for s in sources}

    served_by = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        if attempt > 1:
            request = request.retry_copy()
        result = await llm_service.complete(request)  # LLMError propagates
        served_by = f"{result.provider}/{result.model}"
        try:
            parsed = parse_llm_json(result.text)
        except ValueError:
            parsed = None
        items = unwrap_list(parsed, keys=("claims", "extracted_claims"), item_keys=("claim_text",))
        if not items:
            logger.warning("claim extraction reply unusable (attempt %d/%d)", attempt, _MAX_ATTEMPTS)
            continue
        extracted: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict) or not str(item.get("claim_text") or "").strip():
                continue
            cited_sources = [sid for sid in _as_list(item.get("supporting_source_ids")) if sid in valid_source_ids]
            cited_chunks = [cid for cid in _as_list(item.get("supporting_chunk_ids")) if cid in valid_chunk_ids]
            conflicts = list(
                dict.fromkeys(
                    sid
                    for sid in (*_as_list(item.get("conflicts_with")), *_as_list(item.get("contradicting_source_ids")))
                    if sid in valid_source_ids
                )
            )
            status = str(item.get("status", "")).lower()
            if status not in CLAIM_STATUSES:
                status = "inference"
            rationale = str(item.get("rationale", "")).strip()
            if status == "supported" and not (cited_sources or cited_chunks):
                # Self-declared support with no verifiable citation is downgraded, never trusted.
                status = "inference"
                rationale = (rationale + " [Downgraded: cited evidence ids did not match shown chunks.]").strip()
            if conflicts and status == "supported":
                status = "contested"
                rationale = (rationale + " [Contested: cited sources disagree on this claim.]").strip()
            distinct_sources = set(cited_sources) | {chunk_source[cid] for cid in cited_chunks if chunk_source.get(cid)}
            extracted.append(
                {
                    "id": f"claim_{uuid.uuid4().hex[:12]}",
                    "claim_text": str(item["claim_text"]).strip(),
                    "status": status,
                    "category": str(item.get("category", "general")).lower(),
                    # Derived from verifiable citations — the model's own number is ignored.
                    "confidence": citation_confidence(len(distinct_sources)),
                    "supporting_source_ids": cited_sources,
                    "supporting_chunk_ids": cited_chunks,
                    "contradicting_source_ids": conflicts,
                    "rationale": rationale,
                    "extraction_source": "llm",
                    "served_by": served_by,
                }
            )
        if extracted:
            return extracted
        logger.warning("claim extraction reply held no usable claims (attempt %d/%d)", attempt, _MAX_ATTEMPTS)

    raise UnusableModelOutput(
        CLAIMS_EXTRACTION_UNPARSEABLE,
        f"The model's evidence-claim reply could not be used after {_MAX_ATTEMPTS} attempts; "
        "no hypothesis list was substituted.",
        attempts=_MAX_ATTEMPTS,
        served_by=served_by,
    )
