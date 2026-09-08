"""Study Design Copilot API — conversational study design, persona-role
suggestions and copilot persona generation, all through LLMService (Rule R3).

No canned engine: when the routing layer is missing or the model's reply is
unusable after one retry, the request fails explicitly with the standard error
envelope (RULES.md R2) so the UI can say so and offer a retry.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from bebshax.api.auth import get_current_user
from bebshax.api.deps import require_study_access, user_owns_study
from bebshax.api.limiter import limiter
from bebshax.auth.models import Users
from bebshax.db.models import EvidenceClaims, Personas, Studies
from bebshax.llm.failures import LLMError
from bebshax.llm.json_utils import parse_llm_json, unwrap_list
from bebshax.llm.prompt_safety import UNTRUSTED_RULE, untrusted_block
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.utils.explicit_failures import LLMUnavailable, UnusableModelOutput
from bebshax.utils.safe_errors import safe_error_summary

logger = logging.getLogger(__name__)

router = APIRouter(tags=["study_copilot"])

# Unusable model replies are retried once with the same request, then refused.
_MAX_MODEL_ATTEMPTS = 2


class CopilotMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class CopilotRequest(BaseModel):
    # Every message is forwarded to the model: the caps bound prompt size.
    messages: list[CopilotMessage] = Field(min_length=1, max_length=60)
    study_type: Optional[str] = Field(default=None, max_length=64)
    study_id: Optional[str] = Field(default=None, max_length=64)


class ResearchGoalCard(BaseModel):
    title: str = "RESEARCH GOAL"
    summary: str
    target_audience: str
    core_hypothesis: str


class PersonaRoleSuggestion(BaseModel):
    id: str
    role: str
    description: str
    count: int = 0
    selected: bool = False


class CopilotResponse(BaseModel):
    reply: str
    suggested_study_type: str = "interviews"
    is_ready_for_approval: bool = False
    research_goal_card: Optional[ResearchGoalCard] = None
    suggested_roles: list[PersonaRoleSuggestion] = Field(default_factory=list)
    # Always the real provenance route ("provider/model") — there is no canned engine.
    served_by: str
    # Only ever "retried_after_unparseable_reply": the model's first reply was
    # unusable and the SAME request was sent once more. Never a template marker.
    fallback_reason: Optional[str] = None
    llm_request_id: Optional[str] = None


class SuggestRolesRequest(BaseModel):
    study_prompt: str = Field(max_length=8000)
    goal: Optional[str] = Field(default=None, max_length=256)
    target_audience: Optional[str] = Field(default=None, max_length=2000)
    study_title: Optional[str] = Field(default=None, max_length=256)


SYSTEM_PROMPT = """You are BebshaX Study Design Copilot, an expert AI product researcher for synthetic persona validation.
Your goal is to guide the user in defining a high-impact research study through brief, friendly, focused dialogue.

You handle ANY business idea — SaaS, consumer apps, marketplaces, physical products, services, B2B tools, food & beverage, fashion, fintech, healthcare, logistics, education, and more.

Behavior:
1. Turn 1 (Initial idea):
   - Acknowledge their exact business idea and the specific market they are targeting.
   - Identify the most relevant study type: User Interviews (for demand/willingness-to-pay/friction), Concept Testing, Message Testing, or A/B Test.
   - Ask 1 crisp clarifying question about the target geography, specific customer segment, or a key assumption they need to validate.
2. Turn 2 (Clarification received):
   - Ask a follow-up question about buyer demographics, use-case frequency, or the primary risk/concern they are most worried about.
3. Turn 3+ (Once enough details are present):
   - Output your final synthesis in JSON (see format below).
   - Create a clear, executive-level RESEARCH GOAL tailored to their exact business idea.
   - Always end the summary with: "Does this capture what you're looking for?"
   - Suggest 4-8 highly relevant persona roles that would be meaningful for their study. Make roles specific to their business context.

Output Format:
ALWAYS return ONLY valid JSON — no markdown, no surrounding text, just the JSON object:

For turns 1-2 (still gathering info):
{
  "reply": "Conversational explanation and question to display to the user",
  "suggested_study_type": "interviews",
  "is_ready_for_approval": false,
  "research_goal_card": null,
  "suggested_roles": []
}

For turn 3+ (ready to synthesize):
{
  "reply": "I've synthesized your inputs into a focused research goal proposal below:",
  "suggested_study_type": "interviews",
  "is_ready_for_approval": true,
  "research_goal_card": {
    "title": "RESEARCH GOAL",
    "summary": "You want to research whether [specific hypothesis about their actual business]. [Key decision they need to make]. Does this capture what you're looking for?",
    "target_audience": "[Specific audience description based on their context]",
    "core_hypothesis": "[Core assumption to validate]"
  },
  "suggested_roles": [
    {
      "id": "role_1",
      "role": "ROLE TITLE IN CAPS",
      "description": "Specific reason this persona type is crucial for validating the exact hypotheses in their business context",
      "count": 3,
      "selected": true
    },
    {
      "id": "role_2",
      "role": "ANOTHER ROLE",
      "description": "Why this role is relevant",
      "count": 3,
      "selected": true
    }
  ]
}

CRITICAL RULES:
- NEVER hardcode student or Bangladesh context unless the user specifically mentioned it.
- Tailor ALL responses to the user's exact business idea and market.
- suggested_roles must be relevant to the user's specific product/service, not generic student roles.
- Return ONLY raw JSON. No markdown code blocks. No explanatory text outside the JSON.
"""

PERSONA_GENERATION_PROMPT = """You are BebshaX Persona Engine. Generate {count} synthetic user personas for a product research study.

Business Context: {study_prompt}
Target Persona Role: {role_title}
Role Description: {role_description}

Generate realistic, grounded personas for this SPECIFIC business context. Each persona must:
- Be a real person archetype that would plausibly use or be affected by this product/service
- Have demographics appropriate to the business context (not generic)
- Have goals, pain points, and needs tied to the specific product being researched
- Include realistic daily behaviors, income levels, and digital habits matching the context

Return ONLY a valid JSON object (no markdown, no code blocks) with one key, "personas", holding an array of {count} persona object(s):
{
  "personas": [
  {
    "id": "per_{short_name_lowercase}",
    "name": "Full Name",
    "initials": "AB",
    "country_code": "<ISO 3166-1 alpha-2 of where this person lives, taken from the study context>",
    "country_name": "<country name matching country_code>",
    "role_id": "{role_id}",
    "role_title": "{role_title}",
    "archetype": "Descriptive Archetype",
    "tagline": "The [Evocative Label]",
    "demographics": {
      "age": 28,
      "gender": "Female",
      "occupation": "Specific Job Title",
      "income_bracket": "Realistic Income",
      "location": "City, Country",
      "education": "Degree Level"
    },
    "description": "2-3 sentence vivid description of this person in the context of the product",
    "badges": [
      {"label": "RELEVANT LABEL", "value": "Specific value relevant to the business"},
      {"label": "MONTHLY BUDGET", "value": "Realistic amount for this product"},
      {"label": "USAGE PATTERN", "value": "How they would use this product"},
      {"label": "KEY CONCERN", "value": "Their main concern about this product"}
    ],
    "attributes": [
      {
        "category": "Goals",
        "title": "Specific Goal Related to Product",
        "description": "What they want to achieve with this product",
        "provenance_class": "INFERRED",
        "evidence": null
      },
      {
        "category": "Pain Points",
        "title": "Current Frustration",
        "description": "What problem they currently face that this product solves",
        "provenance_class": "INFERRED",
        "evidence": null
      },
      {
        "category": "Needs",
        "title": "Core Need",
        "description": "What they need from this product to adopt it",
        "provenance_class": "INFERRED",
        "evidence": null
      }
    ],
    "critic_notes": "Brief note about realism",
    "generation_model": "openrouter/llm",
    "created_at": "2026-08-24T22:00:00Z",
    "status": "active",
    "version": 1
  }
  ]
}
"""

SUGGEST_ROLES_PROMPT = """You are BebshaX Persona Role Architect. Suggest 8-10 distinct persona roles for user research.

{study_context}

Analyze the business context carefully and suggest persona roles that would provide the most valuable insights for validating this specific product. Consider:
- Primary users of the product
- Secondary stakeholders (payers, influencers, channel partners)
- Edge cases and skeptical users
- Power users vs. casual users
- Different demographic segments relevant to this product, its stated target audience and its market/region

Return ONLY a valid JSON object (no markdown) with one key, "roles", holding the array:
{
  "roles": [
    {
      "id": "role_{short_id}",
      "role": "ROLE NAME IN CAPS (max 4 words)",
      "description": "Specific reason this persona type is essential for validating the product hypothesis. Be concrete about what insights they provide.",
      "count": 3,
      "selected": true
    }
  ]
}

RULES:
- Return all 8-10 roles inside the "roles" array, never a single role
- Make the first 3 roles "selected": true with "count": 3 (primary roles)
- Remaining roles should be "selected": false with "count": 0
- All roles must be directly relevant to the specific product context
- Never suggest generic student/academic roles unless the product is education-related
- Role names should be evocative and specific (e.g., "WEEKEND WARRIOR" not just "USER")
"""


def _route_of(result: Any) -> str:
    provider = getattr(result, "provider", None) or getattr(getattr(result, "provenance", None), "served_by_provider", None)
    model = getattr(result, "model", None) or getattr(getattr(result, "provenance", None), "served_by_model", None)
    return f"{provider}/{model}" if provider else "llm/unknown"


async def _complete_json(
    llm_router: Any,
    llm_req: LLMRequest,
    *,
    accept,
    error_code: str,
    what: str,
) -> tuple[Any, Any, int]:
    """Send ``llm_req``; return ``(parsed, result, attempts)`` once ``accept(parsed)``
    is truthy. One retry with the identical request, then ``UnusableModelOutput``.
    ``LLMError`` propagates untouched (infrastructure is never masked)."""
    last_result = None
    for attempt in range(1, _MAX_MODEL_ATTEMPTS + 1):
        if attempt > 1:
            llm_req = llm_req.retry_copy()
        last_result = await llm_router.complete(llm_req)
        try:
            parsed = parse_llm_json(last_result.text)
        except ValueError:
            parsed = None
        if parsed is not None and accept(parsed):
            return parsed, last_result, attempt
        logger.warning("%s: unusable model reply (attempt %d/%d)", what, attempt, _MAX_MODEL_ATTEMPTS)
    raise UnusableModelOutput(
        error_code,
        f"The model's reply for {what} could not be used after {_MAX_MODEL_ATTEMPTS} attempts; "
        "nothing was substituted. Please try again.",
        attempts=_MAX_MODEL_ATTEMPTS,
        served_by=_route_of(last_result),
    )


def _study_context_block(
    *,
    study_prompt: str | None,
    title: str | None = None,
    goal: str | None = None,
    target_audience: str | None = None,
    pricing_hypothesis: str | None = None,
) -> str:
    """Everything the model should tailor to, as DATA (prompt_safety)."""
    lines = []
    if title:
        lines.append(f"STUDY TITLE: {title}")
    lines.append(f"BUSINESS / PRODUCT IDEA: {study_prompt or ''}")
    if goal:
        lines.append(f"RESEARCH GOAL: {goal}")
    if target_audience:
        lines.append(f"TARGET AUDIENCE: {target_audience}")
    if pricing_hypothesis:
        lines.append(f"PRICING HYPOTHESIS: {pricing_hypothesis}")
    return untrusted_block("STUDY_CONTEXT", "\n".join(lines), source="study")


def _roles_from(raw_roles: Any) -> list[PersonaRoleSuggestion]:
    roles: list[PersonaRoleSuggestion] = []
    # json_object mode forces an object at the top level: accept {"roles": [...]},
    # any single-list wrapper, or one bare role object (all observed live).
    for r in unwrap_list(raw_roles, keys=("roles", "persona_roles", "suggestions"), item_keys=("role",)):
        if not isinstance(r, dict):
            continue
        role = str(r.get("role") or "").strip()
        if not role:
            continue  # a role without a name is not a role
        try:
            count = int(r.get("count", 0) or 0)
        except (TypeError, ValueError):
            count = 0
        roles.append(
            PersonaRoleSuggestion(
                id=str(r.get("id") or f"role_{len(roles) + 1}"),
                role=role,
                description=str(r.get("description") or ""),
                count=max(0, min(count, 10)),
                selected=bool(r.get("selected", False)),
            )
        )
    return roles


@router.post("/study/copilot", response_model=CopilotResponse)
@limiter.limit("30/minute")
async def study_design_copilot(
    body: CopilotRequest,
    request: Request,
    current_user: Users = Depends(get_current_user),
) -> CopilotResponse:
    """Conversational study design copilot. Every reply is a routed LLM reply."""
    # A study id in the body is a tenant-owned reference: read gate (this route
    # writes nothing, so the demo's public read allowance still applies).
    if body.study_id:
        gate_sessionmaker = getattr(request.app.state, "db_sessionmaker", None)
        if gate_sessionmaker:
            async with gate_sessionmaker() as gate_session:
                study_row = await gate_session.get(Studies, body.study_id)
                if study_row is None or not user_owns_study(study_row, current_user):
                    raise HTTPException(status_code=404, detail="study not found")

    llm_router = getattr(request.app.state, "llm_router", None)
    if llm_router is None:
        raise LLMUnavailable("The study copilot")

    chat_messages: list[ChatMessage] = [ChatMessage(role="system", content=SYSTEM_PROMPT + "\n" + UNTRUSTED_RULE)]
    for m in body.messages:
        chat_messages.append(ChatMessage(role=m.role, content=m.content))
    llm_req = LLMRequest(
        task=TaskType.STRUCTURED_OUTPUT,
        messages=chat_messages,
        json_mode=True,
        temperature=0.5,
    )

    def _accept(parsed: Any) -> bool:
        return isinstance(parsed, dict) and bool(str(parsed.get("reply") or "").strip())

    parsed, result, attempts = await _complete_json(
        llm_router, llm_req, accept=_accept, error_code="copilot_reply_unparseable", what="the copilot reply"
    )

    ready = bool(parsed.get("is_ready_for_approval", False))
    raw_card = parsed.get("research_goal_card")
    card = None
    if ready and isinstance(raw_card, dict) and str(raw_card.get("summary") or "").strip():
        card = ResearchGoalCard(
            title=str(raw_card.get("title") or "RESEARCH GOAL"),
            summary=str(raw_card["summary"]),
            target_audience=str(raw_card.get("target_audience") or ""),
            core_hypothesis=str(raw_card.get("core_hypothesis") or ""),
        )
    # A "ready" flag without a real card is not approvable.
    ready = ready and card is not None

    return CopilotResponse(
        reply=str(parsed.get("reply", "")),
        suggested_study_type=str(parsed.get("suggested_study_type") or "interviews"),
        is_ready_for_approval=ready,
        research_goal_card=card,
        suggested_roles=_roles_from(parsed.get("suggested_roles")),
        served_by=_route_of(result),
        fallback_reason="retried_after_unparseable_reply" if attempts > 1 else None,
        llm_request_id=getattr(getattr(result, "provenance", None), "request_id", None),
    )


@router.post("/study/suggest-roles", response_model=list[PersonaRoleSuggestion])
@limiter.limit("30/minute")
async def suggest_persona_roles(
    body: SuggestRolesRequest,
    request: Request,
    current_user: Users = Depends(get_current_user),
) -> list[PersonaRoleSuggestion]:
    """Persona roles for THIS study (idea + goal + audience), written by the model.

    Authenticated only: this spends real LLM budget and is only ever reached
    from the signed-in study workflow.
    """
    llm_router = getattr(request.app.state, "llm_router", None)
    if llm_router is None:
        raise LLMUnavailable("Persona role suggestion")
    if not (body.study_prompt or "").strip():
        raise HTTPException(status_code=400, detail="Describe the business idea first.")

    context = _study_context_block(
        study_prompt=body.study_prompt,
        title=body.study_title,
        goal=body.goal,
        target_audience=body.target_audience,
    )
    # NOTE: .replace(), not .format() — the template embeds a JSON example
    # whose braces make str.format() raise KeyError.
    prompt = SUGGEST_ROLES_PROMPT.replace("{study_context}", context)
    llm_req = LLMRequest(
        task=TaskType.STRUCTURED_OUTPUT,
        messages=[
            ChatMessage(
                role="system",
                content="You are a business research persona strategist. Return only valid JSON. " + UNTRUSTED_RULE,
            ),
            ChatMessage(role="user", content=prompt),
        ],
        json_mode=True,
        temperature=0.6,
        max_output_tokens=2500,
    )

    def _accept(parsed: Any) -> bool:
        return bool(_roles_from(parsed))

    parsed, _result, _attempts = await _complete_json(
        llm_router, llm_req, accept=_accept, error_code="roles_unparseable", what="persona role suggestions"
    )
    return _roles_from(parsed)


class GeneratePersonasRequest(BaseModel):
    study_id: Optional[str] = Field(default=None, max_length=64)
    study_prompt: Optional[str] = Field(default=None, max_length=8000)
    study_title: Optional[str] = Field(default=None, max_length=256)
    # One LLM call per selected role.
    roles: list[PersonaRoleSuggestion] = Field(default_factory=list, max_length=10)


def _get_initials(name: str) -> str:
    parts = name.split()
    return "".join(p[0].upper() for p in parts[:2]) if len(parts) >= 2 else name[:2].upper()


# Claims shown to the model on the copilot persona path; mirrors the generator's
# own prompt budget so a large study cannot blow the context window.
_COPILOT_CLAIM_LIMIT = 6


def _apply_evidence_grounding(
    persona: dict[str, Any], evidence_claims: list[dict[str, Any]]
) -> None:
    """Score grounding from verified citations and label the basis honestly.

    OBSERVED means "cited a claim we actually showed the model" — citation
    existence, not semantic entailment. Unverifiable citations are stripped and
    the attribute downgrades to INFERRED (downgrade-only, never upgraded).
    ``grounding_basis`` tells the UI whether 0.0 is a measurement or an absence
    of evidence, so a bare "0% Grounded" badge cannot imply the former.
    """
    alias_to_claim = {c["alias"]: c["claim_id"] for c in evidence_claims}
    attributes = [a for a in (persona.get("attributes") or []) if isinstance(a, dict)]
    observed = 0
    for attr in attributes:
        raw = attr.get("evidence")
        cited = raw if isinstance(raw, list) else ([raw] if isinstance(raw, str) else [])
        resolved = list(
            dict.fromkeys(
                alias_to_claim[str(cid).strip().upper()]
                for cid in cited
                if str(cid).strip().upper() in alias_to_claim
            )
        )
        if resolved:
            attr["evidence"] = resolved
            attr["provenance_class"] = "OBSERVED"
            observed += 1
        else:
            attr["evidence"] = None
            attr["provenance_class"] = "INFERRED"

    persona["grounding_ratio"] = round(observed / len(attributes), 4) if attributes else 0.0
    persona["consistency_score"] = 0.0
    persona["evidence_claim_count"] = len(evidence_claims)
    persona["grounding_basis"] = (
        "citations_verified" if evidence_claims else "no_evidence_retrieved"
    )


class FailedRole(BaseModel):
    role_id: str
    role: str
    error_code: str
    detail: str


class GeneratePersonasResponse(BaseModel):
    personas: list[dict[str, Any]]
    # Roles the model could not produce personas for — reported, never replaced
    # by a skeleton. Empty when every selected role succeeded.
    failed_roles: list[FailedRole] = Field(default_factory=list)
    served_by: list[str] = Field(default_factory=list)


def _clean_persona_payload(p: dict[str, Any]) -> dict[str, Any]:
    """Drop empty/placeholder values so a missing field stays missing downstream."""
    demographics = p.get("demographics")
    if isinstance(demographics, dict):
        p["demographics"] = {k: v for k, v in demographics.items() if v not in (None, "", [], {})}
    else:
        p["demographics"] = {}
    for key in ("badges", "attributes"):
        if not isinstance(p.get(key), list):
            p[key] = []
    p.pop("created_at", None)  # the server owns timestamps
    return p


async def _generate_persona_via_llm(
    llm_router: Any,
    role: PersonaRoleSuggestion,
    *,
    context_block: str,
    count: int,
    evidence_claims: Optional[list[dict[str, Any]]] = None,
    other_roles: Optional[list[str]] = None,
    avoid_names: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Personas for one role, written by the model for THIS study's context.

    ``other_roles`` are the sibling roles generated for the same study, so each
    persona is written to be distinct from them; ``avoid_names`` are names the
    study already uses (a regeneration after a duplicate)."""
    # NOTE: .replace(), not .format() — the template embeds a JSON example
    # whose braces make str.format() raise KeyError.
    prompt = (
        PERSONA_GENERATION_PROMPT
        .replace("{count}", str(count))
        .replace("{study_prompt}", "see STUDY_CONTEXT below")
        .replace("{role_title}", role.role or "")
        .replace("{role_description}", role.description or "")
        .replace("{role_id}", role.id or "")
    )
    prompt += "\n\n" + context_block
    if other_roles:
        prompt += (
            "\n\nOther persona roles being generated for this same study: "
            + "; ".join(other_roles)
            + ". Make this persona clearly distinct from them in name, occupation, life situation and voice."
        )
    if avoid_names:
        prompt += (
            "\n\nNames already used by other personas in this study — do NOT reuse them or close variants: "
            + ", ".join(avoid_names)
            + "."
        )
    if evidence_claims:
        claim_lines = "\n".join(f"- {c['alias']}: {c['claim_text']}" for c in evidence_claims)
        prompt += (
            "\n\n"
            + untrusted_block("EVIDENCE_CLAIMS", claim_lines, source="evidence_claims")
            + "\nWhen an attribute is directly supported by one of these claims, set its "
            '"evidence" field to an array of the supporting claim ids (e.g. ["C1"]) and '
            'its "provenance_class" to "OBSERVED". Never invent claim ids; leave '
            '"evidence" null when no listed claim supports the attribute.'
        )
    llm_req = LLMRequest(
        task=TaskType.PERSONA_NARRATIVE,
        messages=[
            ChatMessage(
                role="system",
                content=(
                    "You are a synthetic persona generator. Return ONLY a valid JSON object, no markdown. "
                    "Keep every description under 40 words so the full array always fits in the response. "
                    "Derive country, city, currency and habits from the study context — never assume a region. "
                    + UNTRUSTED_RULE
                ),
            ),
            ChatMessage(role="user", content=prompt),
        ],
        json_mode=True,
        temperature=0.8,
        max_output_tokens=4096,
    )

    def _accept(parsed: Any) -> bool:
        items = unwrap_list(parsed, keys=("personas",), item_keys=("name",))
        return any(isinstance(p, dict) and str(p.get("name") or "").strip() for p in items)

    parsed, result, _attempts = await _complete_json(
        llm_router,
        llm_req,
        accept=_accept,
        error_code="persona_generation_unparseable",
        what=f"personas for role '{role.role}'",
    )
    items = unwrap_list(parsed, keys=("personas",), item_keys=("name",))
    served_by = _route_of(result)
    personas: list[dict[str, Any]] = []
    for p in items:
        if not isinstance(p, dict) or not str(p.get("name") or "").strip():
            continue
        p = _clean_persona_payload(p)
        p["role_id"] = role.id
        p["role_title"] = role.role
        p["generation_model"] = served_by  # the real route, never the prompt's example
        p["status"] = "active"
        p["version"] = 1
        if not p.get("initials"):
            p["initials"] = _get_initials(str(p["name"]))
        personas.append(p)
    return personas[:count]


def _attr_titles(persona: dict[str, Any], category: str) -> list[str]:
    return [
        str(a.get("title"))
        for a in persona.get("attributes", [])
        if isinstance(a, dict) and a.get("category") == category and a.get("title")
    ]


def _name_key(persona: dict[str, Any]) -> str:
    return " ".join(str(persona.get("name") or "").lower().split())


async def _dedupe_persona_names(
    personas: list[dict[str, Any]],
    roles: list[PersonaRoleSuggestion],
    regenerate,
) -> list[dict[str, Any]]:
    """Roles are generated concurrently, so two roles can come back with the
    same person (observed live: two 'Maria Chen's with incompatible bios). The
    later duplicates are regenerated ONCE with the used names excluded; a
    duplicate that survives is kept but flagged — never silently renamed."""
    seen: dict[str, int] = {}
    duplicates: list[int] = []
    for index, persona in enumerate(personas):
        key = _name_key(persona)
        if key and key in seen:
            duplicates.append(index)
        elif key:
            seen[key] = index
    if not duplicates:
        return personas

    roles_by_id = {r.id: r for r in roles}
    used_names = sorted({str(p.get("name")) for p in personas if p.get("name")})
    for index in duplicates:
        persona = personas[index]
        role = roles_by_id.get(str(persona.get("role_id") or ""))
        replacement: Optional[dict[str, Any]] = None
        if role is not None:
            regenerated, _failed, _exc = await regenerate(role, used_names)
            fresh = [p for p in regenerated if _name_key(p) and _name_key(p) not in seen]
            replacement = fresh[0] if fresh else None
        if replacement is not None:
            personas[index] = replacement
            seen[_name_key(replacement)] = index
            used_names.append(str(replacement.get("name")))
        else:
            warnings = persona.setdefault("validation_warnings", [])
            if isinstance(warnings, list):
                warnings.append(f"duplicate_name: another persona in this study is also named {persona.get('name')}")
    return personas


@router.post("/study/generate-personas", response_model=GeneratePersonasResponse)
@limiter.limit("20/minute")
async def generate_study_personas(
    body: GeneratePersonasRequest,
    request: Request,
    current_user: Users = Depends(get_current_user),
) -> GeneratePersonasResponse:
    """Generate synthetic personas for the selected roles from THIS study's context.

    Every persona is model-written. A role whose generation fails is reported in
    ``failed_roles`` (never replaced by a skeleton); if every role fails the
    request fails explicitly. Superseded personas of the study are archived so
    the study has one set of current personas.
    """
    # Ownership gate BEFORE any LLM spend or writes: a client-supplied
    # study_id must never inject personas into another tenant's study.
    evidence_claims: list[dict[str, Any]] = []
    study_row: Optional[Studies] = None
    if body.study_id:
        gate_sessionmaker = getattr(request.app.state, "db_sessionmaker", None)
        if gate_sessionmaker:
            async with gate_sessionmaker() as gate_session:
                study_row = await gate_session.get(Studies, body.study_id)
                require_study_access(
                    study_row,
                    current_user,
                    write=True,
                    read_only_detail=(
                        "This is a read-only example study — "
                        "create your own study to generate personas."
                    ),
                )
                claim_rows = (
                    (
                        await gate_session.execute(
                            select(EvidenceClaims)
                            .where(EvidenceClaims.study_id == body.study_id)
                            .order_by(EvidenceClaims.confidence.desc())
                            .limit(_COPILOT_CLAIM_LIMIT)
                        )
                    )
                    .scalars()
                    .all()
                )
                evidence_claims = [
                    {"alias": f"C{i + 1}", "claim_id": c.id, "claim_text": c.claim_text or ""}
                    for i, c in enumerate(claim_rows)
                ]

    study_prompt = (body.study_prompt or (study_row.prompt if study_row else None) or "").strip()
    if not study_prompt:
        raise HTTPException(status_code=400, detail="Describe the business idea before generating personas.")
    selected_roles = [r for r in body.roles if r.selected or r.count > 0] or body.roles[:3]
    if not selected_roles:
        raise HTTPException(status_code=400, detail="Select at least one persona role.")
    llm_router = getattr(request.app.state, "llm_router", None)
    if llm_router is None:
        raise LLMUnavailable("Persona generation")
    context_block = _study_context_block(
        study_prompt=study_prompt,
        title=body.study_title or (study_row.title if study_row else None),
        goal=(study_row.goal if study_row else None),
        target_audience=(study_row.target_audience if study_row else None),
        pricing_hypothesis=(study_row.pricing_hypothesis if study_row else None),
    )

    async def _one_role(
        role: PersonaRoleSuggestion, avoid_names: Optional[list[str]] = None
    ) -> tuple[list[dict[str, Any]], Optional[FailedRole], Optional[BaseException]]:
        count = max(1, min(role.count, 3))
        siblings = [r.role for r in selected_roles if r.id != role.id and r.role]
        try:
            return await _generate_persona_via_llm(
                llm_router,
                role,
                context_block=context_block,
                count=count,
                evidence_claims=evidence_claims,
                other_roles=siblings,
                avoid_names=avoid_names,
            ), None, None
        except UnusableModelOutput as exc:
            return [], FailedRole(role_id=role.id, role=role.role, error_code=exc.error_code, detail=exc.detail), exc
        except LLMError as exc:
            logger.warning("persona generation failed for role %s: %s", role.id, safe_error_summary(exc))
            return [], FailedRole(
                role_id=role.id,
                role=role.role,
                error_code="all_candidates_failed" if type(exc).__name__ == "AllCandidatesFailed" else "llm_error",
                detail="No AI route could serve this role right now.",
            ), exc

    results = await asyncio.gather(*(_one_role(r) for r in selected_roles))
    all_personas: list[dict[str, Any]] = []
    failed_roles: list[FailedRole] = []
    errors: list[BaseException] = []
    for personas, failed, exc in results:
        all_personas.extend(personas)
        if failed is not None:
            failed_roles.append(failed)
        if exc is not None:
            errors.append(exc)
    all_personas = await _dedupe_persona_names(all_personas, selected_roles, _one_role)
    if not all_personas:
        # Every role failed: surface the real failure (503/413/502 envelope).
        raise errors[-1]

    # Grounding is computed from verified citations only — never self-reported.
    for p in all_personas:
        _apply_evidence_grounding(p, evidence_claims)

    # Persist: archive superseded personas, store ONLY what the model produced.
    db_sessionmaker = getattr(request.app.state, "db_sessionmaker", None)
    if db_sessionmaker and body.study_id:
        try:
            async with db_sessionmaker() as db_session:
                study = await db_session.get(Studies, body.study_id)
                await db_session.execute(
                    update(Personas)
                    .where(Personas.study_id == body.study_id, Personas.status != "archived")
                    .values(status="archived")
                )
                for p in all_personas:
                    # SERVER owns persona identity (LLM-suggested ids collide across studies).
                    p_id = f"per_{uuid.uuid4().hex[:12]}"
                    p["id"] = p_id
                    p["study_id"] = body.study_id
                    demographics = p.get("demographics") or {}
                    personality = p.get("personality") if isinstance(p.get("personality"), dict) else None
                    db_session.add(
                        Personas(
                            id=p_id,
                            study_id=body.study_id,
                            user_id=study.user_id if study else None,
                            owner_id=(study.user_id if study else None) or "usr_system_holder",
                            name=str(p.get("name")),
                            status="active",
                            version=1,
                            generation_model=p.get("generation_model"),
                            archetype=p.get("archetype") or p.get("role_title"),
                            tagline=p.get("tagline"),
                            country_code=p.get("country_code"),
                            personality=personality or None,
                            detailed_attributes=p.get("detailed_attributes") or {},
                            demographics=demographics,
                            bio=p.get("description"),
                            quote=p.get("quote"),
                            goals=_attr_titles(p, "Goals"),
                            needs=_attr_titles(p, "Needs"),
                            pain_points=_attr_titles(p, "Pain Points"),
                            grounding_score=float(p.get("grounding_ratio", 0.0)),
                        )
                    )
                if study:
                    study.personas_data = all_personas
                    study.persona_ids = [p["id"] for p in all_personas]
                    study.persona_count = len(all_personas)
                    study.step = max(study.step or 1, 2)
                await db_session.commit()
        except Exception:
            # Personas the UI shows but the DB doesn't have make every later
            # interview 404 — this must never fail silently.
            logger.error(
                "persona persistence failed for study %s — generated personas will 404 in interviews",
                body.study_id,
                exc_info=True,
            )
            raise HTTPException(status_code=503, detail="Personas were generated but could not be saved. Please retry.")

    return GeneratePersonasResponse(
        personas=all_personas,
        failed_roles=failed_roles,
        served_by=sorted({p.get("generation_model") for p in all_personas if p.get("generation_model")}),
    )
