"""Study Design Copilot API — routes conversational research prompts and persona role suggestions to FreeLLMpool (Rule R3)."""

from __future__ import annotations

import json
import re
import random
import uuid
from typing import Any, Literal, Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from bebshax.llm.types import ChatMessage, LLMRequest, TaskType

router = APIRouter(tags=["study_copilot"])


class CopilotMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CopilotRequest(BaseModel):
    messages: list[CopilotMessage] = Field(min_length=1)
    study_type: Optional[str] = None
    study_id: Optional[str] = None


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
    served_by: str = "routed_llm"


class SuggestRolesRequest(BaseModel):
    study_prompt: str
    goal: Optional[str] = None
    target_audience: Optional[str] = None


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

Return ONLY a valid JSON array (no markdown, no code blocks):
[
  {
    "id": "per_{short_name_lowercase}",
    "name": "Full Name",
    "initials": "AB",
    "country_code": "US",
    "country_name": "United States",
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
        "provenance_class": "OBSERVED",
        "evidence": null
      },
      {
        "category": "Pain Points",
        "title": "Current Frustration",
        "description": "What problem they currently face that this product solves",
        "provenance_class": "OBSERVED",
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
    "consistency_score": 0.96,
    "grounding_ratio": 0.94,
    "critic_notes": "Brief note about realism",
    "generation_model": "openrouter/llm",
    "created_at": "2026-08-24T22:00:00Z",
    "status": "active",
    "version": 1
  }
]
"""

SUGGEST_ROLES_PROMPT = """You are BebshaX Persona Role Architect. Suggest 8-10 distinct persona roles for user research.

Business/Product Context: {study_prompt}

Analyze the business context carefully and suggest persona roles that would provide the most valuable insights for validating this specific product. Consider:
- Primary users of the product
- Secondary stakeholders (payers, influencers, channel partners)
- Edge cases and skeptical users
- Power users vs. casual users
- Different demographic segments relevant to this product

Return ONLY a valid JSON array (no markdown):
[
  {
    "id": "role_{short_id}",
    "role": "ROLE NAME IN CAPS (max 4 words)",
    "description": "Specific reason this persona type is essential for validating the product hypothesis. Be concrete about what insights they provide.",
    "count": 3,
    "selected": true
  }
]

RULES:
- Make the first 3 roles "selected": true with "count": 3 (primary roles)
- Remaining roles should be "selected": false with "count": 0
- All roles must be directly relevant to the specific product context
- Never suggest generic student/academic roles unless the product is education-related
- Role names should be evocative and specific (e.g., "WEEKEND WARRIOR" not just "USER")
"""


def _generate_fallback_response(messages: list[CopilotMessage]) -> CopilotResponse:
    """Deterministic fallback copilot dialog — context-aware for any business idea."""
    user_turns = [m for m in messages if m.role == "user"]
    turn_count = len(user_turns)
    latest_user_text = user_turns[-1].content.strip() if user_turns else ""
    first_user_text = user_turns[0].content.strip() if user_turns else ""
    combined_text = (first_user_text + " " + latest_user_text).lower()

    # Detect business domain from keywords
    has_pricing = any(kw in combined_text for kw in ["taka", "dollar", "$", "price", "cost", "month", "subscription", "plan", "free"])
    has_students = any(kw in combined_text for kw in ["student", "school", "college", "university", "study"])
    has_food = any(kw in combined_text for kw in ["food", "restaurant", "delivery", "meal", "eat", "chef", "recipe", "cuisine"])
    has_ecommerce = any(kw in combined_text for kw in ["shop", "sell", "buy", "product", "store", "marketplace", "ecommerce", "fashion"])
    has_health = any(kw in combined_text for kw in ["health", "fitness", "gym", "workout", "diet", "wellness", "doctor", "medical"])
    has_fintech = any(kw in combined_text for kw in ["payment", "banking", "finance", "loan", "invest", "money", "wallet", "crypto"])
    has_b2b = any(kw in combined_text for kw in ["business", "enterprise", "company", "saas", "team", "office", "workflow", "productivity"])

    # Build context-aware product description
    if has_food:
        product_type = "food/restaurant service"
        audience_q = "Who are the primary customers — home cooks, busy professionals, families, or a specific demographic? And what region or city are you targeting first?"
        followup_q = "What's the main value proposition — convenience, cost savings, quality, or something else? And what price point are you considering?"
    elif has_health:
        product_type = "health & wellness product"
        audience_q = "Who is your primary target user — fitness enthusiasts, people with specific health conditions, or a broader wellness audience? And what geography are you focusing on?"
        followup_q = "Is this a consumer product or B2B (e.g., gyms, clinics)? And what's the rough price point you're considering?"
    elif has_fintech:
        product_type = "fintech product"
        audience_q = "Who is your primary user — individuals, small businesses, or enterprises? And what geography or income segment are you targeting?"
        followup_q = "What is the core financial problem you're solving — payments, savings, credit, or investments? And what regulatory environment applies?"
    elif has_ecommerce:
        product_type = "e-commerce or marketplace"
        audience_q = "Who are your primary buyers — consumers or businesses? And what product category or niche are you focused on?"
        followup_q = "Are you a marketplace (connecting buyers and sellers) or a direct retailer? And what's your target geography and price range?"
    elif has_b2b:
        product_type = "B2B SaaS or business tool"
        audience_q = "What size companies are you targeting — SMBs, mid-market, or enterprise? And what industry or department does this serve?"
        followup_q = "What is the primary workflow or problem being solved? And what's your pricing model — per seat, per usage, or flat subscription?"
    elif has_students:
        product_type = "education or student-focused product"
        audience_q = "What level of students — K-12, university, or professional learners? And what geography or institution type are you targeting?"
        followup_q = "Is this a B2C product for students directly, or B2B (schools/universities)? And what's the price point you're validating?"
    else:
        product_type = "product or service"
        audience_q = "Who is your primary target user — what's their age range, lifestyle, or professional context? And what geography are you launching in first?"
        followup_q = "What's the core problem you're solving for them, and what's the price point or business model you're validating?"

    if turn_count == 1:
        reply = (
            f"Got it — you're exploring a {product_type}{' with a target pricing model' if has_pricing else ''}. "
            f"User Interviews are ideal here to uncover mental models, key objections, and real willingness to pay.\n\n"
            f"{audience_q}"
        )
        return CopilotResponse(
            reply=reply,
            suggested_study_type="interviews",
            is_ready_for_approval=False,
            research_goal_card=None,
            suggested_roles=[],
            served_by="bebshax/copilot-engine",
        )

    elif turn_count == 2:
        return CopilotResponse(
            reply=followup_q,
            suggested_study_type="interviews",
            is_ready_for_approval=False,
            research_goal_card=None,
            suggested_roles=[],
            served_by="bebshax/copilot-engine",
        )

    else:
        # Generate context-aware summary
        summary = (
            f"Validate whether your {product_type} solves a genuine need for target users "
            f"and determine demand{' at your target price point' if has_pricing else ''}. "
            f"Does this capture what you're looking for?"
        )

        # Generate context-aware roles
        if has_food:
            roles = _make_roles([
                ("role_hungry_professional", "BUSY PROFESSIONAL", "Time-pressed professional who orders food regularly and values convenience over price — core paying customer.", 3, True),
                ("role_home_cook", "HOME COOK", "Cooking enthusiast who compares your product against cooking at home — key value perception benchmark.", 3, True),
                ("role_family_planner", "FAMILY MEAL PLANNER", "Parent managing family nutrition and budget — represents group/family subscription potential.", 3, True),
                ("role_health_conscious", "HEALTH-CONSCIOUS EATER", "Health-focused user with specific dietary needs — tests premium tier and ingredient transparency demands.", 0, False),
                ("role_price_sensitive", "PRICE-SENSITIVE DINER", "Value-maximizer who compares cost per meal vs. alternatives — tests pricing floor.", 0, False),
                ("role_weekend_indulger", "WEEKEND INDULGER", "Casual user who treats themselves occasionally — tests occasional-use conversion.", 0, False),
            ])
        elif has_health:
            roles = _make_roles([
                ("role_fitness_enthusiast", "FITNESS ENTHUSIAST", "Regular gym-goer or active lifestyle person — primary power user who validates core features.", 3, True),
                ("role_health_beginner", "WELLNESS BEGINNER", "Person just starting their health journey — tests onboarding ease and motivational hooks.", 3, True),
                ("role_chronic_condition", "CHRONIC CONDITION USER", "Person managing a specific health condition — tests specialized feature depth and clinical accuracy.", 3, True),
                ("role_time_poor_professional", "TIME-POOR PROFESSIONAL", "High-income, low-time user who values efficiency over effort — validates premium tier.", 0, False),
                ("role_skeptic", "HEALTH SKEPTIC", "Person who has tried and failed at health apps before — reveals key churn drivers.", 0, False),
            ])
        elif has_fintech:
            roles = _make_roles([
                ("role_early_adopter_pro", "EARLY ADOPTER PRO", "Tech-savvy individual comfortable with financial apps — validates core product assumptions and API depth.", 3, True),
                ("role_small_biz_owner", "SMALL BUSINESS OWNER", "SMB operator managing cash flow and payments — high-value B2B2C segment.", 3, True),
                ("role_underbanked_user", "UNDERBANKED USER", "Person with limited access to traditional banking — tests financial inclusion positioning.", 3, True),
                ("role_security_skeptic", "SECURITY SKEPTIC", "Privacy-first user concerned about data and fraud — reveals trust barriers to adoption.", 0, False),
                ("role_high_net_worth", "HIGH NET WORTH USER", "Affluent user with complex financial needs — tests premium tier ceiling.", 0, False),
            ])
        elif has_ecommerce:
            roles = _make_roles([
                ("role_impulse_buyer", "IMPULSE BUYER", "Discovery-driven shopper who buys based on recommendations — tests conversion and merchandising.", 3, True),
                ("role_research_first", "RESEARCH-FIRST BUYER", "Methodical shopper who compares options — tests trust signals, reviews, and pricing clarity.", 3, True),
                ("role_loyal_repeater", "LOYAL REPEATER", "Returning customer seeking value — tests retention mechanics, loyalty programs, and subscription offers.", 3, True),
                ("role_deal_hunter", "DEAL HUNTER", "Discount-motivated buyer — tests promotional sensitivity and price floor.", 0, False),
                ("role_premium_seeker", "PREMIUM SEEKER", "Quality-over-price buyer — tests premium positioning and brand perception.", 0, False),
            ])
        elif has_b2b:
            roles = _make_roles([
                ("role_decision_maker", "BUDGET DECISION MAKER", "Manager or executive who approves tool purchases — validates ROI narrative and business case.", 3, True),
                ("role_power_user", "DAILY POWER USER", "Individual contributor who uses the tool most — validates UX depth and workflow integration.", 3, True),
                ("role_it_evaluator", "IT SECURITY EVALUATOR", "Tech/security gatekeeping role — tests compliance, integration complexity, and enterprise requirements.", 3, True),
                ("role_champion", "INTERNAL CHAMPION", "Early adopter who advocates for the tool — tests viral/referral mechanics.", 0, False),
                ("role_skeptic_user", "CHANGE-RESISTANT USER", "Employee reluctant to adopt new tools — reveals adoption barriers and onboarding gaps.", 0, False),
            ])
        elif has_students:
            roles = _make_roles([
                ("role_uni_student", "UNIVERSITY STUDENT", "Core target user — validates product-market fit, UX, and willingness to pay.", 3, True),
                ("role_college_applicant", "COLLEGE APPLICANT", "High-stakes test-taker with strong motivation — validates premium tier and urgency.", 3, True),
                ("role_busy_high_schooler", "BUSY HIGH SCHOOLER", "Time-pressed student balancing multiple priorities — tests core value delivery.", 3, True),
                ("role_parental_buyer", "PARENTAL BUYER", "Parent paying for their child's tools — validates pricing framing and trust signals.", 0, False),
                ("role_budget_student", "BUDGET-CONSCIOUS STUDENT", "Price-sensitive student — tests pricing floor and free tier design.", 0, False),
            ])
        else:
            roles = _make_roles([
                ("role_primary_user", "PRIMARY USER", "Core target user who will use the product most — validates product-market fit and core value proposition.", 3, True),
                ("role_early_adopter", "EARLY ADOPTER", "Tech-forward user open to new solutions — validates initial demand and first-mover appeal.", 3, True),
                ("role_price_conscious", "PRICE-CONSCIOUS USER", "Budget-sensitive potential customer — validates pricing model and value-to-cost ratio.", 3, True),
                ("role_skeptic", "SKEPTICAL NON-USER", "Person who currently uses a competitor or workaround — reveals switching barriers.", 0, False),
                ("role_power_user", "POWER USER", "Heavy user who needs advanced features — validates depth and scalability.", 0, False),
                ("role_influencer", "INFLUENCER OR REFERRER", "Person who recommends products to others — validates viral/word-of-mouth potential.", 0, False),
            ])

        card = ResearchGoalCard(
            title="RESEARCH GOAL",
            summary=summary,
            target_audience=f"Target users of the {product_type}",
            core_hypothesis=f"Demand and product-market fit for the {product_type}",
        )

        return CopilotResponse(
            reply="I've synthesized your inputs into a focused research goal proposal below:",
            suggested_study_type="interviews",
            is_ready_for_approval=True,
            research_goal_card=card,
            suggested_roles=roles,
            served_by="bebshax/copilot-engine",
        )


def _make_roles(role_specs: list[tuple]) -> list[PersonaRoleSuggestion]:
    return [
        PersonaRoleSuggestion(id=id_, role=role, description=desc, count=count, selected=selected)
        for id_, role, desc, count, selected in role_specs
    ]


@router.post("/study/copilot", response_model=CopilotResponse)
async def study_design_copilot(body: CopilotRequest, request: Request) -> CopilotResponse:
    """Conversational study design copilot running through FreeLLMpool/OpenRouter with fallback."""
    llm_router = getattr(request.app.state, "llm_router", None)

    if llm_router is not None:
        try:
            chat_messages: list[ChatMessage] = [
                ChatMessage(role="system", content=SYSTEM_PROMPT),
            ]
            for m in body.messages:
                chat_messages.append(ChatMessage(role=m.role, content=m.content))

            llm_req = LLMRequest(
                task=TaskType.STRUCTURED_OUTPUT,
                messages=chat_messages,
                json_mode=True,
                temperature=0.5,
            )
            result = await llm_router.complete(llm_req)

            # Parse LLM JSON — strip markdown fences if any
            cleaned_text = result.text.strip()
            if cleaned_text.startswith("```"):
                cleaned_text = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned_text)
                cleaned_text = re.sub(r"\n?```$", "", cleaned_text).strip()

            parsed = json.loads(cleaned_text)
            reply = parsed.get("reply", "")
            study_type = parsed.get("suggested_study_type", "interviews")
            ready = parsed.get("is_ready_for_approval", False)
            raw_card = parsed.get("research_goal_card")
            raw_roles = parsed.get("suggested_roles", [])

            card = None
            if ready and raw_card:
                card = ResearchGoalCard(
                    title=raw_card.get("title", "RESEARCH GOAL"),
                    summary=raw_card.get("summary", ""),
                    target_audience=raw_card.get("target_audience", "Broad target market"),
                    core_hypothesis=raw_card.get("core_hypothesis", "Core value proposition"),
                )

            roles: list[PersonaRoleSuggestion] = []
            if raw_roles:
                for r in raw_roles:
                    roles.append(
                        PersonaRoleSuggestion(
                            id=r.get("id", f"role_{len(roles)}"),
                            role=r.get("role", "TARGET USER"),
                            description=r.get("description", ""),
                            count=r.get("count", 0),
                            selected=r.get("selected", False),
                        )
                    )

            return CopilotResponse(
                reply=reply,
                suggested_study_type=study_type,
                is_ready_for_approval=ready,
                research_goal_card=card,
                suggested_roles=roles,
                served_by=f"{result.provider}/{result.model}",
            )
        except Exception:
            # Safe fail-soft fallback (Rule R2, R3, R6)
            pass

    return _generate_fallback_response(body.messages)


@router.post("/study/suggest-roles", response_model=list[PersonaRoleSuggestion])
async def suggest_persona_roles(body: SuggestRolesRequest, request: Request) -> list[PersonaRoleSuggestion]:
    """Generates suggested persona roles for any research study context via LLM."""
    llm_router = getattr(request.app.state, "llm_router", None)

    if llm_router is not None:
        try:
            prompt = SUGGEST_ROLES_PROMPT.format(study_prompt=body.study_prompt)
            chat_messages = [
                ChatMessage(role="system", content="You are a business research persona strategist. Return only valid JSON arrays."),
                ChatMessage(role="user", content=prompt),
            ]
            llm_req = LLMRequest(
                task=TaskType.STRUCTURED_OUTPUT,
                messages=chat_messages,
                json_mode=True,
                temperature=0.6,
            )
            result = await llm_router.complete(llm_req)
            cleaned = result.text.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
                cleaned = re.sub(r"\n?```$", "", cleaned).strip()
            parsed = json.loads(cleaned)
            if isinstance(parsed, list) and parsed:
                return [
                    PersonaRoleSuggestion(
                        id=r.get("id", f"role_{i}"),
                        role=r.get("role", "TARGET USER"),
                        description=r.get("description", ""),
                        count=r.get("count", 0),
                        selected=r.get("selected", False),
                    )
                    for i, r in enumerate(parsed)
                ]
        except Exception:
            pass

    # Fallback: generate context-aware roles based on study prompt keywords
    fallback = _generate_fallback_response([CopilotMessage(role="user", content=body.study_prompt)])
    if fallback.suggested_roles:
        return fallback.suggested_roles
    # Generic catch-all roles
    return _make_roles([
        ("role_primary_user", "PRIMARY USER", "Core target user for this product — validates primary product-market fit.", 3, True),
        ("role_early_adopter", "EARLY ADOPTER", "Forward-thinking user who validates initial demand and first-mover appeal.", 3, True),
        ("role_budget_user", "PRICE-CONSCIOUS USER", "Budget-sensitive user who validates pricing strategy.", 3, True),
        ("role_skeptic", "SKEPTICAL USER", "Person using a competitor or workaround — reveals switching barriers.", 0, False),
        ("role_power_user", "POWER USER", "Advanced user who validates depth and extensibility.", 0, False),
    ])


class PersonaBadgePayload(BaseModel):
    label: str
    value: str


class GeneratePersonasRequest(BaseModel):
    study_id: Optional[str] = None
    study_prompt: Optional[str] = None
    study_title: Optional[str] = None
    roles: list[PersonaRoleSuggestion] = Field(default_factory=list)


def _get_initials(name: str) -> str:
    parts = name.split()
    return "".join(p[0].upper() for p in parts[:2]) if len(parts) >= 2 else name[:2].upper()


async def _generate_persona_via_llm(
    llm_router: Any,
    role: PersonaRoleSuggestion,
    study_prompt: str,
    count: int,
) -> list[dict[str, Any]]:
    """Use LLM to generate contextual personas for the given role and study prompt."""
    prompt = PERSONA_GENERATION_PROMPT.format(
        count=count,
        study_prompt=study_prompt,
        role_title=role.role,
        role_description=role.description,
        role_id=role.id,
    )
    chat_messages = [
        ChatMessage(role="system", content="You are a synthetic persona generator. Return ONLY a valid JSON array, no markdown."),
        ChatMessage(role="user", content=prompt),
    ]
    llm_req = LLMRequest(
        task=TaskType.PERSONA_NARRATIVE,
        messages=chat_messages,
        json_mode=True,
        temperature=0.8,
    )
    result = await llm_router.complete(llm_req)
    cleaned = result.text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, list):
        parsed = [parsed]
    # Tag each persona with generation metadata
    for p in parsed:
        p["role_id"] = role.id
        p["role_title"] = role.role
        p["business_id"] = "biz_default"
        p["generation_model"] = f"{result.provider}/{result.model}"
        p["status"] = "active"
        p["version"] = 1
        if "initials" not in p or not p["initials"]:
            p["initials"] = _get_initials(p.get("name", "UN"))
    return parsed


@router.post("/study/generate-personas", response_model=list[dict[str, Any]])
async def generate_study_personas(body: GeneratePersonasRequest, request: Request) -> list[dict[str, Any]]:
    """Generates and grounds synthetic personas conditioned on study prompt and selected roles via LLM."""
    llm_router = getattr(request.app.state, "llm_router", None)
    study_prompt = body.study_prompt or "General product/service research study"
    selected_roles = [r for r in body.roles if r.selected or r.count > 0]
    if not selected_roles:
        selected_roles = body.roles[:3] if body.roles else []

    all_personas: list[dict[str, Any]] = []

    if llm_router is not None and selected_roles:
        for role in selected_roles:
            count = max(1, min(role.count, 5))
            try:
                personas = await _generate_persona_via_llm(llm_router, role, study_prompt, count)
                all_personas.extend(personas)
            except Exception:
                all_personas.append(_make_skeleton_persona(role, study_prompt))

    if not all_personas:
        all_personas = [_make_skeleton_persona(r, study_prompt) for r in selected_roles[:5]]

    # If study_id provided, persist personas into DB Personas table and update Studies record
    db_sessionmaker = getattr(request.app.state, "db_sessionmaker", None)
    if db_sessionmaker and body.study_id and all_personas:
        try:
            async with db_sessionmaker() as db_session:
                from bebshax.db.models import Personas, Studies
                study = await db_session.get(Studies, body.study_id)
                for p in all_personas:
                    p_id = p.get("id") or f"per_{uuid.uuid4().hex[:12]}"
                    p["id"] = p_id
                    p["study_id"] = body.study_id
                    existing = await db_session.get(Personas, p_id)
                    if not existing:
                        db_p = Personas(
                            id=p_id,
                            study_id=body.study_id,
                            user_id=study.user_id if study else None,
                            name=p.get("name", "Target User"),
                            status="active",
                            version=1,
                            generation_model=p.get("generation_model", "copilot/llm"),
                            archetype=p.get("archetype", p.get("role_title", "User")),
                            demographics=p.get("demographics", {}),
                            bio=p.get("description", ""),
                            quote=p.get("tagline", ""),
                            goals=[a.get("title") for a in p.get("attributes", []) if a.get("category") == "Goals"] or ["Efficiency", "Convenience"],
                            needs=[a.get("title") for a in p.get("attributes", []) if a.get("category") == "Needs"] or ["Frictionless onboarding"],
                            pain_points=[a.get("title") for a in p.get("attributes", []) if a.get("category") == "Pain Points"] or ["Manual workarounds", "High cost"],
                            grounding_score=float(p.get("grounding_ratio", 0.92)),
                        )
                        db_session.add(db_p)
                if study:
                    study.personas_data = all_personas
                    study.persona_ids = [p["id"] for p in all_personas]
                    study.persona_count = len(all_personas)
                    study.step = max(study.step or 1, 2)
                await db_session.commit()
        except Exception:
            pass

    return all_personas


def _make_skeleton_persona(role: PersonaRoleSuggestion, study_prompt: str) -> dict[str, Any]:
    """Create a minimal skeleton persona when LLM is unavailable."""
    short = role.id.replace("role_", "").replace("_", "")[:8]
    first_names = ["Alex", "Jordan", "Sam", "Taylor", "Morgan", "Casey", "Riley", "Drew"]
    last_names = ["Smith", "Johnson", "Lee", "Garcia", "Patel", "Chen", "Kim", "Brown"]
    name = f"{random.choice(first_names)} {random.choice(last_names)}"
    return {
        "id": f"per_{short}_{random.randint(100, 999)}",
        "business_id": "biz_default",
        "name": name,
        "initials": _get_initials(name),
        "country_code": "US",
        "country_name": "United States",
        "role_id": role.id,
        "role_title": role.role,
        "archetype": role.role.title(),
        "tagline": f"The {role.role.title().split()[0]} Profile",
        "demographics": {
            "age": random.randint(22, 45),
            "gender": "Female" if random.random() > 0.5 else "Male",
            "occupation": role.role.title(),
            "income_bracket": "Middle income",
            "location": "Metro area",
            "education": "Bachelor's degree",
        },
        "description": f"A {role.role.lower()} persona relevant to: {study_prompt[:100]}.",
        "badges": [
            {"label": "ROLE", "value": role.role},
            {"label": "CONTEXT", "value": study_prompt[:80]},
        ],
        "attributes": [
            {
                "category": "Goals",
                "title": f"Achieve value from {role.role.lower()}",
                "description": role.description,
                "provenance_class": "INFERRED",
                "evidence": None,
            }
        ],
        "consistency_score": 0.85,
        "grounding_ratio": 0.80,
        "critic_notes": "Skeleton persona — regenerate with LLM for full detail.",
        "generation_model": "bebshax/skeleton-fallback",
        "created_at": "2026-08-24T22:00:00Z",
        "status": "active",
        "version": 1,
    }
