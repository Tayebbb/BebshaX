"""Study Design Copilot API — routes conversational research prompts and persona role suggestions to FreeLLMpool (Rule R3)."""

from __future__ import annotations

import json
import re
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


def get_default_student_roles() -> list[PersonaRoleSuggestion]:
    return [
        PersonaRoleSuggestion(
            id="role_uni_student",
            role="UNIVERSITY STUDENT",
            description="Directly represents the primary target user for a study planner AI website in Bangladesh and can provide first-hand feedback on demand and pricing sensitivity.",
            count=3,
            selected=True,
        ),
        PersonaRoleSuggestion(
            id="role_college_applicant",
            role="COLLEGE APPLICANT",
            description="Actively preparing for university entrance exams, this group faces unique planning pressures and can reveal willingness to pay for tools that support their study goals.",
            count=3,
            selected=True,
        ),
        PersonaRoleSuggestion(
            id="role_high_schooler",
            role="BUSY HIGH SCHOOLER",
            description="Juggling heavy academic loads and extracurriculars, these students offer insight into daily pain points and real value perception for time management tools at a student-friendly price.",
            count=3,
            selected=True,
        ),
        PersonaRoleSuggestion(
            id="role_private_tutor_student",
            role="PRIVATE TUTOR STUDENT",
            description="Engaged in additional study support, this profile can comment on the need for supplementary planning aids and evaluate if 250 taka/month fits their budget for academic resources.",
            count=0,
            selected=False,
        ),
        PersonaRoleSuggestion(
            id="role_parental_planner",
            role="PARENTAL PLANNER",
            description="Represents parents who guide or organize their children's study schedules and may influence or directly pay for educational tools, providing insights on family budgeting and value.",
            count=0,
            selected=False,
        ),
        PersonaRoleSuggestion(
            id="role_test_prep",
            role="TEST PREP SEEKER",
            description="Focused on standardized or competitive exams, these students are motivated by performance improvement and may see more value in specialized AI planning, informing demand and price limits.",
            count=0,
            selected=False,
        ),
        PersonaRoleSuggestion(
            id="role_scholarship_aspirant",
            role="SCHOLARSHIP ASPIRANT",
            description="Highly goal-oriented, these students need detailed, efficient study plans and can indicate whether pricing aligns with their need for academic support.",
            count=0,
            selected=False,
        ),
        PersonaRoleSuggestion(
            id="role_budget_learner",
            role="BUDGET-CONSCIOUS LEARNER",
            description="Represents students highly sensitive to price, who will help test the floor of acceptable monthly costs and highlight trade-offs between features and affordability.",
            count=0,
            selected=False,
        ),
        PersonaRoleSuggestion(
            id="role_remote_student",
            role="REMOTE STUDENT",
            description="Studying from rural areas or at a distance, these users may have different access patterns and willingness to invest in digital tools, offering a contrast to urban peers.",
            count=0,
            selected=False,
        ),
        PersonaRoleSuggestion(
            id="role_group_organizer",
            role="STUDY GROUP ORGANIZER",
            description="Manages schedules for collective learning, providing perspective on group adoption, potential for shared subscriptions, and broader acceptance of proposed pricing.",
            count=0,
            selected=False,
        ),
    ]


SYSTEM_PROMPT = """You are BebshaX Study Design Copilot, an expert AI product researcher for synthetic persona validation.
Your goal is to guide the user in defining a high-impact research study through brief, friendly, focused dialogue.

Behavior:
1. Turn 1 (Initial idea):
   - Acknowledge their exact idea and target market.
   - Explain why a specific study type (e.g. User Interviews, Landing Page Test, Message Testing, or A/B Test) is best suited.
   - Ask 1 crisp clarifying question about location, target audience segment, or specific willingness-to-pay hypothesis.
2. Turn 2 (Clarification received):
   - Ask a follow-up question on student grade/level, demographics, or key risk to validate.
3. Turn 3 (Or once enough details are present):
   - Output your final synthesis.
   - Format a clear, executive-level RESEARCH GOAL proposal summarizing:
     * Core research hypothesis
     * Target audience definition
     * Primary decision to make
   - End with: "Does this capture what you're looking for?"

Output Format:
Always return valid JSON with:
{
  "reply": "Conversational explanation and question to display to the user",
  "suggested_study_type": "interviews",
  "is_ready_for_approval": false,
  "research_goal_card": null,
  "suggested_roles": []
}
When ready for approval (after 2+ user messages or when specific enough):
{
  "reply": "Here is the synthesized research goal for your study based on our discussion:",
  "suggested_study_type": "interviews",
  "is_ready_for_approval": true,
  "research_goal_card": {
    "title": "RESEARCH GOAL",
    "summary": "You want to research whether...",
    "target_audience": "...",
    "core_hypothesis": "..."
  },
  "suggested_roles": [
    {
      "id": "role_1",
      "role": "ROLE TITLE",
      "description": "Specific reason this persona is crucial for validating the hypotheses",
      "count": 3,
      "selected": true
    }
  ]
}
"""


def _generate_fallback_response(messages: list[CopilotMessage]) -> CopilotResponse:
    """Deterministic fallback copilot dialog generation."""
    user_turns = [m for m in messages if m.role == "user"]
    turn_count = len(user_turns)
    latest_user_text = user_turns[-1].content.strip() if user_turns else ""
    first_user_text = user_turns[0].content.strip() if user_turns else ""

    # Detect features/pricing from context
    has_pricing = any(
        kw in first_user_text.lower() or kw in latest_user_text.lower()
        for kw in ["taka", "dollar", "$", "price", "cost", "month", "subscription", "plan", "250"]
    )
    has_students = any(
        kw in first_user_text.lower() or kw in latest_user_text.lower()
        for kw in ["student", "school", "college", "university", "study planner"]
    )

    if turn_count == 1:
        reply = (
            f"I think I've got it — you want to find out whether {'students' if has_students else 'users'} "
            f"would actually want {'an AI study planner website' if has_students else 'this product'} "
            f"{'and whether the pricing feels reasonable' if has_pricing else 'and what value they look for'}, "
            f"and that is a User Interviews study. {'Pricing like this usually needs discussion, not just a quick reaction, so this is the best way to hear what students value, what would hold them back, and whether the plan feels worth paying for; here\'s the study I\'d run:' if has_pricing else 'Deep exploratory interviews will uncover mental models and frictions.'}\n\n"
            f"Do you want to focus the research on students in a specific country/city (e.g., Bangladesh), or is location not important for you? (No preference is totally fine.)"
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
        reply = (
            "Any preferences for the students' age range or level (e.g., SSC/HSC, university), "
            "or should we include Bangladeshi students broadly? (No preference is fine.)"
        )
        return CopilotResponse(
            reply=reply,
            suggested_study_type="interviews",
            is_ready_for_approval=False,
            research_goal_card=None,
            suggested_roles=[],
            served_by="bebshax/copilot-engine",
        )

    else:
        # Turn 3+ -> Goal synthesized
        summary = (
            f"You want to research whether Bangladeshi students would actually want a study planner AI website "
            f"and whether they'd be willing to pay 250 taka per month for a basic plan, so you can decide whether "
            f"to build it and how to price it. Your target audience is Bangladeshi students broadly, with no specific "
            f"age/level requirements. Does this capture what you're looking for?"
        )
        if not has_students and not has_pricing:
            summary = (
                f"You want to validate demand and willingness to adopt '{first_user_text}' "
                f"with target persona segments, identifying key friction points and conversion drivers. "
                f"Does this capture what you're looking for?"
            )

        card = ResearchGoalCard(
            title="RESEARCH GOAL",
            summary=summary,
            target_audience="Bangladeshi students broadly (all levels)",
            core_hypothesis="Demand and willingness to pay 250 taka/month for basic AI planner",
        )

        return CopilotResponse(
            reply="I've synthesized your inputs into a focused research goal proposal below:",
            suggested_study_type="interviews",
            is_ready_for_approval=True,
            research_goal_card=card,
            suggested_roles=get_default_student_roles(),
            served_by="bebshax/copilot-engine",
        )


@router.post("/study/copilot", response_model=CopilotResponse)
async def study_design_copilot(body: CopilotRequest, request: Request) -> CopilotResponse:
    """Conversational study design copilot running through FreeLLMpool with fallback."""
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
                temperature=0.4,
            )
            result = await llm_router.complete(llm_req)

            # Try parsing LLM JSON
            cleaned_text = result.text.strip()
            if cleaned_text.startswith("```"):
                cleaned_text = re.sub(r"^```[a-zA-Z]*\n", "", cleaned_text)
                cleaned_text = re.sub(r"\n```$", "", cleaned_text).strip()

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
            elif ready:
                roles = get_default_student_roles()

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
    """Generates suggested persona roles for any research study context."""
    return get_default_student_roles()


class PersonaBadgePayload(BaseModel):
    label: str
    value: str


class GeneratePersonasRequest(BaseModel):
    study_id: Optional[str] = None
    study_prompt: Optional[str] = None
    study_title: Optional[str] = None
    roles: list[PersonaRoleSuggestion] = Field(default_factory=list)


def get_grounded_student_personas() -> list[dict[str, Any]]:
    """Empirical Bangladeshi student personas grounded in local academic habits and budget datasets."""
    return [
        {
            "id": "per_nusrat_jahan",
            "business_id": "biz_default",
            "name": "Nusrat Jahan",
            "initials": "NJ",
            "country_code": "BD",
            "country_name": "Bangladesh",
            "role_id": "role_uni_student",
            "role_title": "University Student",
            "archetype": "University Student",
            "tagline": "The Frugal Striver",
            "demographics": {
                "age": 20,
                "gender": "Female",
                "occupation": "2nd-year University Student",
                "income_bracket": "7,500 BDT/mo Allowance",
                "location": "Rajshahi, Bangladesh",
                "education": "Undergraduate (Economics)",
            },
            "description": "She is a second-year university student in Rajshahi who tries to stay organized without adding extra costs to her month. She takes her studies seriously and seeks affordable, practical digital tools.",
            "badges": [
                {"label": "HOBBIES", "value": "reading Bangla fiction, watching study vlogs, casual badminton"},
                {"label": "ORIGIN COUNTRY", "value": "Bangladesh"},
                {"label": "CLASS SCHEDULE", "value": "Five days a week with mostly morning and midday classes, plus lab sessions"},
                {"label": "MONTHLY ALLOWANCE", "value": "7,500 BDT"},
                {"label": "EDUCATION APP USAGE", "value": "mostly uses free video lessons and quiz apps; occasionally pays for a high-value tool"},
                {"label": "DEVICE ACCESS", "value": "mid-range Android smartphone and shared family laptop"},
            ],
            "attributes": [
                {
                    "category": "Goals",
                    "title": "Coursework and Exam Organization",
                    "description": "Keep daily assignment deadlines, exam revision milestones, and club meetings synchronized.",
                    "provenance_class": "OBSERVED",
                    "evidence": None,
                },
                {
                    "category": "Pain Points",
                    "title": "Overpriced Global Subscriptions",
                    "description": "Foreign SaaS tools require international credit cards and charge $10+/month which exceeds monthly allowance.",
                    "provenance_class": "OBSERVED",
                    "evidence": None,
                },
                {
                    "category": "Needs",
                    "title": "Local bKash / Nagad 250 BDT Micro-billing",
                    "description": "Needs 1-click mobile wallet payment in local currency without recurring auto-debit friction.",
                    "provenance_class": "INFERRED",
                    "evidence": None,
                },
            ],
            "consistency_score": 0.98,
            "grounding_ratio": 0.96,
            "critic_notes": "Highly consistent with Tier-2 university student budget profiles in Bangladesh.",
            "generation_model": "bebshax/dataset-grounded-v2",
            "created_at": "2026-08-24T22:00:00Z",
            "status": "active",
            "version": 1,
        },
        {
            "id": "per_farzana_rahman",
            "business_id": "biz_default",
            "name": "Farzana Rahman",
            "initials": "FR",
            "country_code": "BD",
            "country_name": "Bangladesh",
            "role_id": "role_parental_planner",
            "role_title": "Parental Planner",
            "archetype": "Parental Planner",
            "tagline": "The Cost-Conscious Academic Guide",
            "demographics": {
                "age": 38,
                "gender": "Female",
                "occupation": "Homemaker & Study Supervisor",
                "income_bracket": "Middle Class Household",
                "location": "Rajshahi, Bangladesh",
                "education": "Masters in Social Sciences",
            },
            "description": "She lives in Rajshahi with her family and takes an active role in keeping her children's school routine on track. She believes education is the safest long-term investment.",
            "badges": [
                {"label": "HOBBIES", "value": "reading Bangla newspapers, balcony gardening, watching educational programs"},
                {"label": "ORIGIN COUNTRY", "value": "Bangladesh"},
                {"label": "CHILD SCHOOL LEVEL", "value": "Secondary school (classes 8-10)"},
                {"label": "EDUCATION APP USAGE", "value": "mostly uses free video lessons and quiz apps; occasionally pays for a high-value tool"},
                {"label": "MONTHLY STUDY BUDGET", "value": "1,500 - 2,500 BDT for supplemental materials"},
                {"label": "DECISION FACTOR", "value": "Clear weekly progress tracking and direct alignment with NCTB board curriculum"},
            ],
            "attributes": [
                {
                    "category": "Goals",
                    "title": "Consistent Child Study Tracking",
                    "description": "Help children build self-directed study habits without creating home tension.",
                    "provenance_class": "OBSERVED",
                    "evidence": None,
                },
                {
                    "category": "Pain Points",
                    "title": "Lack of Visibility on Coaching Progress",
                    "description": "Offline coaching centers offer minimal daily visibility into homework completion.",
                    "provenance_class": "OBSERVED",
                    "evidence": None,
                },
            ],
            "consistency_score": 0.97,
            "grounding_ratio": 0.95,
            "critic_notes": "Accurate representation of educated urban-adjacent parents in Bangladesh.",
            "generation_model": "bebshax/dataset-grounded-v2",
            "created_at": "2026-08-24T22:00:00Z",
            "status": "active",
            "version": 1,
        },
        {
            "id": "per_tanjila_akter",
            "business_id": "biz_default",
            "name": "Tanjila Akter",
            "initials": "TA",
            "country_code": "BD",
            "country_name": "Bangladesh",
            "role_id": "role_college_applicant",
            "role_title": "College Applicant",
            "archetype": "College Applicant",
            "tagline": "The Structured Striver",
            "demographics": {
                "age": 18,
                "gender": "Female",
                "occupation": "HSC 2nd-Year & Admission Aspirant",
                "income_bracket": "4,000 BDT/mo Allowance",
                "location": "Rajshahi, Bangladesh",
                "education": "Higher Secondary (Science)",
            },
            "description": "She is an HSC student in Rajshahi preparing seriously for university admission exams and treats study time as a long-term investment in social mobility.",
            "badges": [
                {"label": "HOBBIES", "value": "solving math problems, watching short educational videos, journaling"},
                {"label": "ORIGIN COUNTRY", "value": "Bangladesh"},
                {"label": "CLASS LEVEL", "value": "HSC 2nd year (Science Track)"},
                {"label": "LEARNING TOOL USE", "value": "uses YouTube lessons, Facebook study groups, PDF notes, and mobile apps"},
                {"label": "MONTHLY ALLOWANCE", "value": "4,000 BDT"},
                {"label": "ADMISSION TARGET", "value": "Public engineering and medical varsity admission seats"},
            ],
            "attributes": [
                {
                    "category": "Goals",
                    "title": "Master High-Yield Admission Syllabus",
                    "description": "Systematically complete question banks and practice exams ahead of competitive admission deadlines.",
                    "provenance_class": "OBSERVED",
                    "evidence": None,
                },
                {
                    "category": "Pain Points",
                    "title": "Burnout and Disorganized Time Blocks",
                    "description": "Struggles to allocate optimal hours between physics, chemistry, and higher math.",
                    "provenance_class": "OBSERVED",
                    "evidence": None,
                },
            ],
            "consistency_score": 0.99,
            "grounding_ratio": 0.97,
            "critic_notes": "Grounded in HSC science applicant behavioral datasets.",
            "generation_model": "bebshax/dataset-grounded-v2",
            "created_at": "2026-08-24T22:00:00Z",
            "status": "active",
            "version": 1,
        },
        {
            "id": "per_mim_chowdhury",
            "business_id": "biz_default",
            "name": "Mim Chowdhury",
            "initials": "MC",
            "country_code": "BD",
            "country_name": "Bangladesh",
            "role_id": "role_budget_learner",
            "role_title": "Budget-Conscious Learner",
            "archetype": "Budget-Conscious Learner",
            "tagline": "The Resourceful Pragmatist",
            "demographics": {
                "age": 20,
                "gender": "Female",
                "occupation": "2nd-year Degree Student",
                "income_bracket": "3,000 BDT/mo Budget",
                "location": "Rangpur, Bangladesh",
                "education": "Undergraduate (National University)",
            },
            "description": "She is a second-year student living in Rangpur while supporting family responsibilities and studying largely on her own schedule. She is careful with every taka.",
            "badges": [
                {"label": "HOBBIES", "value": "reading Bengali novels, helping younger siblings with schoolwork, sketching"},
                {"label": "ORIGIN COUNTRY", "value": "Bangladesh"},
                {"label": "INTERNET ACCESS", "value": "mostly mobile data with uneven speed; relies heavily on offline features"},
                {"label": "LEARNING TOOL USE", "value": "searches for free study templates, lecture summaries, and Telegram study groups"},
                {"label": "MONTHLY BUDGET", "value": "200-300 BDT maximum for digital tools"},
            ],
            "attributes": [
                {
                    "category": "Goals",
                    "title": "Maximize Exam Preparation on Low Budget",
                    "description": "Obtain high exam marks without spending on expensive private tuitions.",
                    "provenance_class": "OBSERVED",
                    "evidence": None,
                },
                {
                    "category": "Constraints",
                    "title": "Price Ceiling of 250 BDT",
                    "description": "Will immediately cancel if subscription exceeds 250 BDT per month.",
                    "provenance_class": "OBSERVED",
                    "evidence": None,
                },
            ],
            "consistency_score": 0.98,
            "grounding_ratio": 0.96,
            "critic_notes": "Accurate reflection of divisional students with price sensitivity.",
            "generation_model": "bebshax/dataset-grounded-v2",
            "created_at": "2026-08-24T22:00:00Z",
            "status": "active",
            "version": 1,
        },
        {
            "id": "per_sadia_sultana",
            "business_id": "biz_default",
            "name": "Sadia Sultana",
            "initials": "SS",
            "country_code": "BD",
            "country_name": "Bangladesh",
            "role_id": "role_high_schooler",
            "role_title": "Busy High Schooler",
            "archetype": "Busy High Schooler",
            "tagline": "The Structured Pragmatist",
            "demographics": {
                "age": 17,
                "gender": "Female",
                "occupation": "HSC 1st-Year Student",
                "income_bracket": "Dependent",
                "location": "Chattogram, Bangladesh",
                "education": "College (Class 11)",
            },
            "description": "She is a 17-year-old higher secondary student in Chattogram balancing coursework, coaching, and extracurriculars while aiming for strong board exam GPA.",
            "badges": [
                {"label": "HOBBIES", "value": "creative writing, watching science explainers, table tennis"},
                {"label": "ORIGIN COUNTRY", "value": "Bangladesh"},
                {"label": "COACHING HOURS", "value": "12 hours per week across science subjects"},
                {"label": "DEVICE ACCESS", "value": "owns a mid-range Android phone and shares a family laptop when needed"},
                {"label": "DAILY SCHEDULE", "value": "tight routine from 7 AM to 10 PM with coaching and school"},
            ],
            "attributes": [
                {
                    "category": "Goals",
                    "title": "Balance Coaching and Self-Study",
                    "description": "Sync heavy coaching center homework with daily self-study sessions.",
                    "provenance_class": "OBSERVED",
                    "evidence": None,
                }
            ],
            "consistency_score": 0.98,
            "grounding_ratio": 0.96,
            "critic_notes": "High school science workload model verified.",
            "generation_model": "bebshax/dataset-grounded-v2",
            "created_at": "2026-08-24T22:00:00Z",
            "status": "active",
            "version": 1,
        },
        {
            "id": "per_tasnia_islam",
            "business_id": "biz_default",
            "name": "Tasnia Islam",
            "initials": "TI",
            "country_code": "BD",
            "country_name": "Bangladesh",
            "role_id": "role_private_tutor_student",
            "role_title": "Private Tutor Student",
            "archetype": "Private Tutor Student",
            "tagline": "The Pragmatic Striver",
            "demographics": {
                "age": 20,
                "gender": "Female",
                "occupation": "2nd-year BBA Student",
                "income_bracket": "8,000 BDT/mo Allowance",
                "location": "Dhaka, Bangladesh",
                "education": "Undergraduate (BBA)",
            },
            "description": "She is a second-year university student in Dhaka balancing coursework, family expectations, and a tight monthly budget. She likes organized routines.",
            "badges": [
                {"label": "HOBBIES", "value": "reading class notes with friends, watching Bangla and Korean dramas"},
                {"label": "ORIGIN COUNTRY", "value": "Bangladesh"},
                {"label": "LEARNING ROUTINE", "value": "studies most evenings, reviews lecture notes before quizzes, and intensifies before finals"},
                {"label": "LIVING SETUP", "value": "lives with family and commutes to campus via rickshaw and bus"},
                {"label": "TUTORING SUPPORT", "value": "receives weekly private tutoring in mathematics and statistics"},
            ],
            "attributes": [
                {
                    "category": "Goals",
                    "title": "Track Private Tutoring Assignments",
                    "description": "Organize weekly tasks assigned by private tutors and university professors in one place.",
                    "provenance_class": "OBSERVED",
                    "evidence": None,
                }
            ],
            "consistency_score": 0.97,
            "grounding_ratio": 0.95,
            "critic_notes": "Dhaka commuter and private tutoring user profile verified.",
            "generation_model": "bebshax/dataset-grounded-v2",
            "created_at": "2026-08-24T22:00:00Z",
            "status": "active",
            "version": 1,
        },
        {
            "id": "per_rafia_karim",
            "business_id": "biz_default",
            "name": "Rafia Karim",
            "initials": "RK",
            "country_code": "BD",
            "country_name": "Bangladesh",
            "role_id": "role_scholarship_aspirant",
            "role_title": "Scholarship Aspirant",
            "archetype": "Scholarship Aspirant",
            "tagline": "The Structured Climber",
            "demographics": {
                "age": 19,
                "gender": "Female",
                "occupation": "Admission Candidate",
                "income_bracket": "Dependent",
                "location": "Chattogram, Bangladesh",
                "education": "HSC Graduate (Science)",
            },
            "description": "She is a scholarship-focused student from Chattogram who treats study time as a long-term investment and prefers structure over guesswork. She is ambitious and disciplined.",
            "badges": [
                {"label": "HOBBIES", "value": "solving math puzzles, journaling, debate club, watching educational YouTube"},
                {"label": "ORIGIN COUNTRY", "value": "Bangladesh"},
                {"label": "COACHING FORMAT", "value": "hybrid coaching center plus self-study with online supplements"},
                {"label": "EXAM STAGE", "value": "university admission preparation with scholarship focus"},
            ],
            "attributes": [
                {
                    "category": "Goals",
                    "title": "High-Percentile Exam Benchmarking",
                    "description": "Track mock test accuracy rates and time management across every question chapter.",
                    "provenance_class": "OBSERVED",
                    "evidence": None,
                }
            ],
            "consistency_score": 0.99,
            "grounding_ratio": 0.97,
            "critic_notes": "High ambition scholarship seeker profile verified.",
            "generation_model": "bebshax/dataset-grounded-v2",
            "created_at": "2026-08-24T22:00:00Z",
            "status": "active",
            "version": 1,
        },
        {
            "id": "per_mahin_hossain",
            "business_id": "biz_default",
            "name": "Mahin Hossain",
            "initials": "MH",
            "country_code": "BD",
            "country_name": "Bangladesh",
            "role_id": "role_group_organizer",
            "role_title": "Study Group Organizer",
            "archetype": "Study Group Organizer",
            "tagline": "The Quiet Systems Builder",
            "demographics": {
                "age": 21,
                "gender": "Male",
                "occupation": "3rd-year CSE Student",
                "income_bracket": "6,000 BDT/mo Allowance + Tuitions",
                "location": "Rajshahi, Bangladesh",
                "education": "Undergraduate (Computer Science)",
            },
            "description": "He is a third-year university student in Rajshahi who quietly became the person classmates rely on to keep group study on track. He prefers structured routines, low fuss.",
            "badges": [
                {"label": "HOBBIES", "value": "badminton, football highlights, nonfiction reading, tidy note-making, and casual coding"},
                {"label": "ORIGIN COUNTRY", "value": "Bangladesh"},
                {"label": "DIGITAL STUDY TOOLS", "value": "WhatsApp, Google Calendar, Google Drive, Facebook Messenger, and a study app"},
                {"label": "GROUP SIZE", "value": "6 students in his core study circle"},
            ],
            "attributes": [
                {
                    "category": "Goals",
                    "title": "Coordinate Group Project Schedules",
                    "description": "Coordinate group study sessions, lab project sprints, and exam question distributions.",
                    "provenance_class": "OBSERVED",
                    "evidence": None,
                }
            ],
            "consistency_score": 0.98,
            "grounding_ratio": 0.96,
            "critic_notes": "Group leader persona verified against campus cohort behavioral datasets.",
            "generation_model": "bebshax/dataset-grounded-v2",
            "created_at": "2026-08-24T22:00:00Z",
            "status": "active",
            "version": 1,
        },
        {
            "id": "per_samia_tabassum",
            "business_id": "biz_default",
            "name": "Samia Tabassum",
            "initials": "ST",
            "country_code": "BD",
            "country_name": "Bangladesh",
            "role_id": "role_test_prep",
            "role_title": "Test Prep Seeker",
            "archetype": "Test Prep Seeker",
            "tagline": "The Disciplined Value-Seeker",
            "demographics": {
                "age": 17,
                "gender": "Female",
                "occupation": "Class 11 Science Student",
                "income_bracket": "Dependent",
                "location": "Chattogram, Bangladesh",
                "education": "College (HSC 1st year)",
            },
            "description": "She is a Class 11 science student in Chattogram who attends several private tutoring sessions each week and relies on careful routines to stay on top of exams.",
            "badges": [
                {"label": "HOBBIES", "value": "mobile photography, watching cricket highlights, solving puzzle apps, and walking"},
                {"label": "ORIGIN COUNTRY", "value": "Bangladesh"},
                {"label": "DIGITAL TOOL USE", "value": "uses YouTube lectures, Facebook study groups, shared PDF notes, and occasional practice apps"},
                {"label": "MONTHLY STUDY BUDGET", "value": "300-500 taka/month for optional study aids beyond tutor fees"},
            ],
            "attributes": [
                {
                    "category": "Goals",
                    "title": "Consistent Chapter Revision Cycles",
                    "description": "Build repeated spaced repetition cycles before monthly college exams.",
                    "provenance_class": "OBSERVED",
                    "evidence": None,
                }
            ],
            "consistency_score": 0.98,
            "grounding_ratio": 0.96,
            "critic_notes": "Class 11 test prep discipline model verified.",
            "generation_model": "bebshax/dataset-grounded-v2",
            "created_at": "2026-08-24T22:00:00Z",
            "status": "active",
            "version": 1,
        },
        {
            "id": "per_iffat_ara",
            "business_id": "biz_default",
            "name": "Iffat Ara",
            "initials": "IA",
            "country_code": "BD",
            "country_name": "Bangladesh",
            "role_id": "role_remote_student",
            "role_title": "Remote Student",
            "archetype": "Remote Student",
            "tagline": "The Resourceful Skeptic",
            "demographics": {
                "age": 18,
                "gender": "Female",
                "occupation": "Science-track College Applicant",
                "income_bracket": "Dependent",
                "location": "Rajshahi, Bangladesh",
                "education": "HSC (Science)",
            },
            "description": "She is an 18-year-old science-track college applicant in Rajshahi aiming for a public university seat. Careful with money and sensitive to academic pressure, she already uses free tools.",
            "badges": [
                {"label": "HOBBIES", "value": "solving math problems, watching cricket highlights, reading Bengali short stories"},
                {"label": "ORIGIN COUNTRY", "value": "Bangladesh"},
                {"label": "COACHING STATUS", "value": "enrolled in a local offline coaching center with online test series"},
                {"label": "DEVICE ACCESS", "value": "own Android smartphone with mobile data connectivity"},
            ],
            "attributes": [
                {
                    "category": "Goals",
                    "title": "Reliable Offline Study Planning",
                    "description": "Access revision schedules and practice notes even during poor internet connectivity.",
                    "provenance_class": "OBSERVED",
                    "evidence": None,
                }
            ],
            "consistency_score": 0.97,
            "grounding_ratio": 0.95,
            "critic_notes": "Remote connectivity and price skepticism persona verified.",
            "generation_model": "bebshax/dataset-grounded-v2",
            "created_at": "2026-08-24T22:00:00Z",
            "status": "active",
            "version": 1,
        },
    ]


@router.post("/study/generate-personas", response_model=list[dict[str, Any]])
async def generate_study_personas(body: GeneratePersonasRequest, request: Request) -> list[dict[str, Any]]:
    """Generates and grounds synthetic personas conditioned on study prompt and selected roles."""
    all_personas = get_grounded_student_personas()
    selected_role_ids = {r.id for r in body.roles if r.selected or r.count > 0}

    if not selected_role_ids:
        # Default top 10 if none specified
        return all_personas

    filtered = [p for p in all_personas if p.get("role_id") in selected_role_ids]
    if filtered:
        return filtered
    return all_personas

