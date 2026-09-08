"""Grounded synthetic persona generation: the model writes every persona from
THIS study's context, segment statistics and evidence claims.

There is no template path. A persona field the model did not produce stays
absent (None / []) — it is never backfilled from an archetype, a keyword
domain table or a regional default. When the model's reply cannot be used
after one retry the run fails explicitly (``UnusableModelOutput``); when no
LLM is wired it fails explicitly (``LLMUnavailable``); infrastructure failures
(``LLMError``) propagate. RULES.md R2.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from bebshax.llm.json_utils import parse_llm_json, unwrap_list
from bebshax.llm.prompt_safety import UNTRUSTED_RULE, untrusted_json_block
from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.personas.validator import validate_synthetic_persona
from bebshax.utils.explicit_failures import LLMUnavailable, UnusableModelOutput

logger = logging.getLogger(__name__)

PERSONA_GENERATION_UNPARSEABLE = "persona_generation_unparseable"

# One request per whole segment can exceed the output budget — adapters treat
# a budget-exhausted completion as a failed attempt (silent-truncation guard).
# ≤3 personas per request keeps ~1200 tokens/persona under the 4000 ceiling.
_MAX_PERSONAS_PER_REQUEST = 3
# A batch whose reply is unusable is retried once; then the run fails explicitly.
_MAX_ATTEMPTS_PER_BATCH = 2

# Claim groups that carry per-claim provenance classes (the research-critical
# ones); other list fields stay plain strings.
_CLASSED_GROUPS = ("goals", "needs", "pain_points")
_PLAIN_LIST_FIELDS = ("behaviors", "preferences", "motivations", "objections")
_BIG_FIVE = ("openness", "conscientiousness", "extroversion", "agreeableness", "neuroticism")

# Currency hints are DERIVED from the study's own text; nothing is assumed.
_CURRENCY_MARKERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"৳|\bbdt\b|\btaka\b|\btk\.?\b", re.IGNORECASE), "BDT"),
    (re.compile(r"\$|\busd\b|\bdollars?\b", re.IGNORECASE), "USD"),
    (re.compile(r"€|\beur\b|\beuros?\b", re.IGNORECASE), "EUR"),
    (re.compile(r"£|\bgbp\b|\bpounds?\b", re.IGNORECASE), "GBP"),
    (re.compile(r"₹|\binr\b|\brupees?\b", re.IGNORECASE), "INR"),
    (re.compile(r"\bksh\b|\bkes\b|\bshillings?\b", re.IGNORECASE), "KES"),
    (re.compile(r"\brp\b|\bidr\b|\brupiah\b", re.IGNORECASE), "IDR"),
    (re.compile(r"\bngn\b|\bnaira\b|₦", re.IGNORECASE), "NGN"),
)


def _coerce_claim_list(
    raw_list: Any, claim_id_map: dict[str, str]
) -> tuple[list[str], list[dict[str, Any]]]:
    """Normalize one claim group into (plain values, classed claims).

    ``claim_id_map`` maps the prompt aliases actually shown to the model
    ("C1"..) to the real evidence-claim ids, so stored citations stay
    resolvable after generation.

    Same downgrade-only policy as persona/schema.coerce_provenance:
    - cited ids must exist among the shown aliases → OBSERVED;
    - invalid/unknown citations are stripped and the claim downgrades to INFERRED;
    - unknown labels (and bare strings — back-compat) are SYNTHETIC.
    Never upgraded except by a verified citation. Verification checks citation
    existence only, not semantic support — OBSERVED means "cited a shown
    claim", not "entailed by it".
    """
    values: list[str] = []
    classed: list[dict[str, Any]] = []
    if not isinstance(raw_list, list):
        return values, classed
    for item in raw_list:
        if isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            values.append(text)
            classed.append({"value": text, "provenance": "SYNTHETIC", "evidence_ids": []})
            continue
        if not isinstance(item, dict):
            continue
        text = str(item.get("value", "")).strip()
        if not text:
            continue
        label = str(item.get("provenance", "")).strip().upper()
        raw_ids = item.get("evidence_ids") or []
        cited = (
            [str(i).strip().upper() for i in raw_ids] if isinstance(raw_ids, list) else []
        )
        # dedupe, keep order, resolve aliases to the real evidence ids
        resolved = list(
            dict.fromkeys(claim_id_map[cid] for cid in cited if cid in claim_id_map)
        )
        if resolved:
            prov = "OBSERVED"
        elif label == "INFERRED" or label == "OBSERVED":
            # claimed observed but cited nothing verifiable → inference at best
            prov = "INFERRED"
        else:
            prov = "SYNTHETIC"
        values.append(text)
        classed.append({"value": text, "provenance": prov, "evidence_ids": resolved})
    return values, classed


class GeneratedPersonaDraft(BaseModel):
    """Exactly what the model produced, normalised — absent means absent."""

    name: str
    archetype: Optional[str] = None
    tagline: Optional[str] = None
    country_code: Optional[str] = None
    origin_country: Optional[str] = None
    demographics: dict[str, Any] = Field(default_factory=dict)
    bio: Optional[str] = None
    quote: Optional[str] = None
    personality: Optional[dict[str, int]] = None
    detailed_attributes: dict[str, Any] = Field(default_factory=dict)
    domain_attributes: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    goals: list[str] = Field(default_factory=list)
    needs: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    behaviors: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    motivations: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    commercial_profile: dict[str, Any] = Field(default_factory=dict)
    technology_profile: dict[str, Any] = Field(default_factory=dict)
    evidence_citations: list[dict[str, Any]] = Field(default_factory=list)
    dataset_refs: list[dict[str, Any]] = Field(default_factory=list)
    # Honest-by-default: scores are earned by validation, never assumed.
    grounding_score: float = 0.0
    confidence: float = 0.0
    status: str = "ready"
    validation_warnings: list[str] = Field(default_factory=list)
    # The ACTUAL origin: "provider/model" from provenance. Never a label.
    generation_model: Optional[str] = None
    # The segment this persona was generated for (set by the generator).
    segment_id: Optional[str] = None
    segment_name: Optional[str] = None


def calculate_segment_quotas(
    segments: list[Any],
    target_count: int,
    strategy: str = "population_weighted",
) -> dict[str, int]:
    """Calculate the number of personas to generate per segment."""
    if not segments:
        return {}
    if len(segments) == 1:
        return {getattr(segments[0], "id", "seg_0"): target_count}

    if strategy == "equal":
        base = target_count // len(segments)
        rem = target_count % len(segments)
        quotas: dict[str, int] = {}
        for idx, s in enumerate(segments):
            sid = getattr(s, "id", f"seg_{idx}")
            quotas[sid] = base + (1 if idx < rem else 0)
        return quotas

    # Population-weighted using largest remainder method
    total_pct = sum((getattr(s, "population_percentage", 0.0) or 10.0) for s in segments) or 100.0
    exact_shares = [
        (getattr(s, "id", f"seg_{idx}"), (getattr(s, "population_percentage", 0.0) / total_pct) * target_count)
        for idx, s in enumerate(segments)
    ]

    quotas = {}
    remainders = []
    assigned = 0
    for sid, share in exact_shares:
        fl = math.floor(share)
        count = max(1 if target_count >= len(segments) else 0, fl)
        quotas[sid] = count
        assigned += count
        remainders.append((sid, share - fl))

    diff = target_count - assigned
    if diff > 0:
        remainders.sort(key=lambda x: x[1], reverse=True)
        for i in range(diff):
            sid = remainders[i % len(remainders)][0]
            quotas[sid] += 1
    elif diff < 0:
        remainders.sort(key=lambda x: x[1])
        for i in range(abs(diff)):
            sid = remainders[i % len(remainders)][0]
            if quotas[sid] > 1:
                quotas[sid] -= 1

    return quotas


# ---------------------------------------------------------------------------
# Study context → prompt (derived, never assumed)
# ---------------------------------------------------------------------------


def infer_currency_hint(study_ctx: dict[str, Any]) -> Optional[str]:
    """ISO code detected in the study's own pricing/audience text, else None.

    None means the model must infer the market's currency from the target
    audience — we never inject a regional default."""
    blob = " ".join(str(study_ctx.get(k, "") or "") for k in ("pricing_hypothesis", "prompt", "target_audience", "title"))
    for pattern, code in _CURRENCY_MARKERS:
        if pattern.search(blob):
            return code
    return None


def _study_context(study: Any) -> dict[str, Any]:
    ctx = {
        "title": getattr(study, "title", None) or "",
        "prompt": getattr(study, "prompt", None) or "",
        "target_audience": getattr(study, "target_audience", None) or "",
        "pricing_hypothesis": getattr(study, "pricing_hypothesis", None) or "",
    }
    ctx["currency_hint"] = infer_currency_hint(ctx)
    return ctx


def _system_prompt(currency_hint: Optional[str]) -> str:
    currency_rule = (
        f"Use the currency {currency_hint} for every monetary amount (the study's own text uses it)."
        if currency_hint
        else "Infer the market's currency from the target audience and state it as an ISO code in `currency`; never assume a country."
    )
    return (
        "You are BebshaX's synthetic customer persona synthesis engine. Write realistic, "
        "specific personas for THIS study only: every detail must follow from the study "
        "context, the segment statistics and the evidence claims provided. Do not reuse "
        "stock archetypes, do not default to any particular country, city, payment method "
        "or diet — derive them from the inputs. If an attribute cannot be inferred from the "
        "inputs, omit it rather than inventing a generic value.\n"
        f"{UNTRUSTED_RULE}\n"
        "Output valid JSON: {\"personas\": [ ... ]}. Each persona object:\n"
        "  name (str), age (int), occupation (str), location (str: city/region as implied by the target market), "
        "country_code (ISO-2), origin_country (str), tagline (str, ≤12 words, specific to this person), "
        "bio (2-3 sentences), quote (1 first-person sentence), education (str)\n"
        "  personality: {openness, conscientiousness, extroversion, agreeableness, neuroticism} integers 0-100\n"
        "  domain_attributes: object of attributes that matter for THIS product (keys you choose)\n"
        "  constraints: {max_monthly_budget (number), subscription_tolerance, switching_tolerance, "
        "preferred_payment_method, price_sensitivity, time_tolerance}\n"
        "  detailed_attributes: {hobbies, commute_mode, work_schedule, communication_style, daily_activities, "
        "decision_style, financial_attitude, tech_interest, time_management}\n"
        "  goals, needs, pain_points: arrays of {\"value\": str, \"provenance\": \"OBSERVED\"|\"INFERRED\"|\"SYNTHETIC\", "
        "\"evidence_ids\": [ids like \"C1\"]}. OBSERVED only when directly supported by a provided claim — cite it; "
        "INFERRED when deduced from segment/study context; SYNTHETIC for plausible invention. Never fabricate ids.\n"
        "  behaviors, preferences, motivations, objections: arrays of strings\n"
        "  monthly_budget (number), currency (ISO code), price_sensitivity (str), "
        "primary_devices (array), platforms (array), tech_familiarity (str)\n"
        f"Rules: {currency_rule} Ages and budgets must fall within the segment bounds when given. "
        "Personas within one segment must differ from each other in occupation, routine and voice."
    )


# ---------------------------------------------------------------------------
# Normalisation — what the model wrote, nothing more
# ---------------------------------------------------------------------------


def _clean_str(value: Any) -> Optional[str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _clean_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+", value)
        if match:
            return int(match.group(0))
    return None


def _clean_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:[.,]\d+)?", value.replace(",", ""))
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                return None
    return None


def _clean_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _clean_str(item.get("value") if isinstance(item, dict) else item)
        if text:
            out.append(text)
    return out


def _clean_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in value.items() if v not in (None, "", [], {})}


def _clean_personality(value: Any) -> Optional[dict[str, int]]:
    if not isinstance(value, dict):
        return None
    scores: dict[str, int] = {}
    for trait in _BIG_FIVE:
        score = _clean_int(value.get(trait))
        if score is not None:
            scores[trait] = max(0, min(100, score))
    return scores or None


def _normalise_persona(
    p_raw: dict[str, Any],
    *,
    seg_char: dict[str, Any],
    claims: list[Any],
    claim_id_map: dict[str, str],
    served_by: str,
    currency_hint: Optional[str],
) -> Optional[GeneratedPersonaDraft]:
    """One model-produced persona → draft. Returns None when the object is
    unusable (no name); never fills a missing field with a default."""
    name = _clean_str(p_raw.get("name"))
    if not name or len(name) < 2:
        return None

    age = _clean_int(p_raw.get("age"))
    occupation = _clean_str(p_raw.get("occupation"))
    location = _clean_str(p_raw.get("location"))
    education = _clean_str(p_raw.get("education"))

    currency = _clean_str(p_raw.get("currency"))
    currency = currency.upper() if currency else currency_hint
    budget = _clean_number(p_raw.get("monthly_budget"))
    if budget is None:
        budget = _clean_number(p_raw.get("monthly_budget_bdt"))
        if budget is not None and currency is None:
            currency = "BDT"

    constraints = _clean_dict(p_raw.get("constraints"))
    if budget is not None and "max_monthly_budget" not in constraints:
        constraints["max_monthly_budget"] = budget

    domain_attrs = _clean_dict(p_raw.get("domain_attributes"))
    detailed = _clean_dict(p_raw.get("detailed_attributes"))
    if domain_attrs:
        detailed["domain_attributes"] = domain_attrs
    if constraints:
        detailed["constraints"] = constraints

    claim_values: dict[str, list[str]] = {}
    claim_provenance: dict[str, list[dict[str, Any]]] = {}
    for group in _CLASSED_GROUPS:
        vals, classed = _coerce_claim_list(p_raw.get(group), claim_id_map)
        claim_values[group] = vals
        claim_provenance[group] = classed
    detailed["claim_provenance"] = claim_provenance

    claim_by_id = {getattr(c, "id", ""): c for c in claims}
    cited_ids = sorted(
        {
            eid
            for entries in claim_provenance.values()
            for entry in entries
            for eid in entry.get("evidence_ids", [])
            if eid in claim_by_id
        }
    )
    matched_citations = [
        {
            "claim_id": cid,
            "claim_text": getattr(claim_by_id[cid], "claim_text", ""),
            "category": getattr(claim_by_id[cid], "category", "general"),
            "confidence": getattr(claim_by_id[cid], "confidence", 0.0),
        }
        for cid in cited_ids
    ]

    commercial: dict[str, Any] = {}
    if budget is not None:
        commercial["monthly_budget"] = budget
        if currency:
            commercial["currency"] = currency
        if currency == "BDT":
            commercial["monthly_budget_bdt"] = budget  # consumers that read the BDT key
    for key in ("price_sensitivity", "payment_preference"):
        text = _clean_str(p_raw.get(key))
        if text:
            commercial[key] = text
    if constraints:
        commercial["constraints"] = constraints

    technology: dict[str, Any] = {}
    devices = _clean_str_list(p_raw.get("primary_devices"))
    platforms = _clean_str_list(p_raw.get("platforms"))
    familiarity = _clean_str(p_raw.get("tech_familiarity"))
    if devices:
        technology["primary_devices"] = devices
    if platforms:
        technology["platforms"] = platforms
    if familiarity:
        technology["familiarity"] = familiarity

    demographics: dict[str, Any] = {}
    for key, value in (
        ("age", age),
        ("occupation", occupation),
        ("location", location),
        ("education", education),
    ):
        if value is not None:
            demographics[key] = value
    if budget is not None:
        demographics["income_or_budget"] = f"{budget:g} {currency}/mo" if currency else f"{budget:g}/mo"

    validation = validate_synthetic_persona(
        {
            "name": name,
            "demographics": demographics,
            "goals": claim_values["goals"],
            "needs": claim_values["needs"],
            "pain_points": claim_values["pain_points"],
            "behaviors": _clean_str_list(p_raw.get("behaviors")),
            "commercial_profile": commercial,
            "evidence_citations": matched_citations,
            "claim_provenance": claim_provenance,
        },
        seg_char,
        claims,
    )

    country_code = _clean_str(p_raw.get("country_code"))
    dataset_refs = (
        [{"variable": "monthly_budget", "value": budget, "currency": currency, "source": "Market Segment"}]
        if budget is not None
        else []
    )
    return GeneratedPersonaDraft(
        name=name,
        archetype=occupation,
        tagline=_clean_str(p_raw.get("tagline")),
        country_code=country_code.upper()[:8] if country_code else None,
        origin_country=_clean_str(p_raw.get("origin_country")),
        demographics=demographics,
        bio=_clean_str(p_raw.get("bio")),
        quote=_clean_str(p_raw.get("quote")),
        personality=_clean_personality(p_raw.get("personality")),
        detailed_attributes=detailed,
        domain_attributes=domain_attrs,
        constraints=constraints,
        goals=claim_values["goals"],
        needs=claim_values["needs"],
        pain_points=claim_values["pain_points"],
        behaviors=_clean_str_list(p_raw.get("behaviors")),
        preferences=_clean_str_list(p_raw.get("preferences")),
        motivations=_clean_str_list(p_raw.get("motivations")),
        objections=_clean_str_list(p_raw.get("objections")),
        commercial_profile=commercial,
        technology_profile=technology,
        evidence_citations=matched_citations,
        dataset_refs=dataset_refs,
        grounding_score=validation.grounding_score,
        confidence=validation.confidence,
        status=validation.status,
        validation_warnings=validation.warnings,
        generation_model=served_by,
    )


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def _served_by(result: Any) -> str:
    prov = getattr(result, "provenance", None)
    provider = getattr(prov, "served_by_provider", None)
    model = getattr(prov, "served_by_model", None)
    return f"{provider}/{model}" if provider else "llm/unknown"


async def _process_segment(
    seg: Any,
    count_for_seg: int,
    study_ctx: dict[str, Any],
    claims: list[Any],
    llm_service: LLMService,
) -> list[GeneratedPersonaDraft]:
    """All personas for one segment, in ≤3-persona requests. An unusable reply
    is retried once per batch; a remaining shortfall is an explicit failure."""
    seg_char = getattr(seg, "characteristics", {}) or {}
    seg_name = getattr(seg, "name", "Segment")
    currency_hint = study_ctx.get("currency_hint")

    shown_claims = claims[:6]
    claim_id_map = {f"C{i + 1}": (getattr(c, "id", "") or f"C{i + 1}") for i, c in enumerate(shown_claims)}
    base_payload = {
        "study_context": {k: v for k, v in study_ctx.items() if k != "currency_hint"},
        "segment": {
            "name": seg_name,
            "cluster_label": getattr(seg, "cluster_label", None),
            "population_percentage": getattr(seg, "population_percentage", None),
            "characteristics": seg_char,
        },
        "evidence_claims": [
            {"id": f"C{i + 1}", "text": getattr(c, "claim_text", ""), "category": getattr(c, "category", "general")}
            for i, c in enumerate(shown_claims)
        ],
    }
    system_prompt = _system_prompt(currency_hint)

    drafts: list[GeneratedPersonaDraft] = []
    remaining = count_for_seg
    attempts_total = 0
    last_served_by: Optional[str] = None
    while remaining > 0:
        batch_count = min(remaining, _MAX_PERSONAS_PER_REQUEST)
        batch_drafts: list[GeneratedPersonaDraft] = []
        for _attempt in range(_MAX_ATTEMPTS_PER_BATCH):
            attempts_total += 1
            request = LLMRequest(
                task=TaskType.PERSONA_GENERATION,
                messages=[
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(
                        role="user",
                        content=(
                            untrusted_json_block(
                                "STUDY_INPUTS", {**base_payload, "count_to_generate": batch_count},
                                source="study+segment+evidence",
                            )
                            + f"\n\nGenerate exactly {batch_count} distinct persona(s) for the segment above."
                        ),
                    ),
                ],
                json_mode=True,
                # 0.75, not 0.3: low temperature makes every segment's personas
                # converge on the same phrasing — diversity is a quality metric.
                temperature=0.75,
                max_output_tokens=min(1200 * batch_count, 4000),
            )
            result = await llm_service.complete(request)  # LLMError propagates (R2/R6)
            last_served_by = _served_by(result)
            try:
                parsed = parse_llm_json(result.text)
            except ValueError:
                parsed = None
            raw_list = unwrap_list(parsed, keys=("personas",), item_keys=("name",))
            if not raw_list:
                logger.warning("persona reply for segment %s unusable (attempt %d)", seg_name, _attempt + 1)
                continue
            for p_raw in raw_list[:batch_count]:
                if not isinstance(p_raw, dict):
                    continue
                draft = _normalise_persona(
                    p_raw,
                    seg_char=seg_char,
                    claims=claims,
                    claim_id_map=claim_id_map,
                    served_by=last_served_by,
                    currency_hint=currency_hint,
                )
                if draft is not None:
                    draft.segment_id = getattr(seg, "id", None)
                    draft.segment_name = seg_name
                    batch_drafts.append(draft)
            if batch_drafts:
                break
        if not batch_drafts:
            raise UnusableModelOutput(
                PERSONA_GENERATION_UNPARSEABLE,
                f"The model's reply for segment '{seg_name}' contained no usable persona after "
                f"{_MAX_ATTEMPTS_PER_BATCH} attempts; nothing was substituted.",
                attempts=attempts_total,
                served_by=last_served_by,
                extra={"segment": seg_name, "requested": count_for_seg, "produced": len(drafts)},
            )
        drafts.extend(batch_drafts)
        remaining -= len(batch_drafts)
    return drafts[:count_for_seg]


async def generate_personas_for_study(
    study: Any,
    segments: list[Any],
    target_count: int = 6,
    distribution_strategy: str = "population_weighted",
    datasets: list[Any] | None = None,
    evidence_claims: list[Any] | None = None,
    llm_service: Optional[LLMService] = None,
) -> list[GeneratedPersonaDraft]:
    """Generate synthetic personas across the study's segments.

    Raises ``ValueError`` (no segments), ``LLMUnavailable`` (no LLM wired),
    ``UnusableModelOutput`` (reply unusable after retry) or any ``LLMError``.
    Never returns fewer personas than requested and never a template."""
    if not segments:
        raise ValueError("Cannot generate personas: study has no market segments. Run segmentation first.")
    if llm_service is None:
        raise LLMUnavailable("Persona generation")

    quotas = calculate_segment_quotas(segments, target_count, distribution_strategy)
    claims = list(evidence_claims or [])
    study_ctx = _study_context(study)

    seg_specs = [(seg, quotas.get(getattr(seg, "id", ""), 1)) for seg in segments]
    coros = [
        _process_segment(seg, count_for_seg, study_ctx, claims, llm_service)
        for seg, count_for_seg in seg_specs
        if count_for_seg > 0
    ]
    # Segments are independent — run concurrently; the pool semaphore caps
    # real parallelism. Output order follows segment declaration order.
    seg_results = await asyncio.gather(*coros, return_exceptions=True)

    all_generated: list[GeneratedPersonaDraft] = []
    for seg_result in seg_results:
        if isinstance(seg_result, BaseException):
            raise seg_result
        all_generated.extend(seg_result)
    return all_generated


__all__ = [
    "PERSONA_GENERATION_UNPARSEABLE",
    "GeneratedPersonaDraft",
    "calculate_segment_quotas",
    "generate_personas_for_study",
    "infer_currency_hint",
]
