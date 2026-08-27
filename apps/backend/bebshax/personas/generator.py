"""Grounded synthetic persona generation engine with quota allocation and fallback."""

from __future__ import annotations

import json
import logging
import math
import random
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from bebshax.llm.failures import AllCandidatesFailed, ContextWindowExceeded
from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.personas.validator import validate_synthetic_persona

logger = logging.getLogger(__name__)

# Honest origin label for template-built personas — rows must never claim an
# LLM produced them (M-series honesty rules).
TEMPLATE_FALLBACK_MODEL = "deterministic-template-fallback"

# One request per whole segment can exceed the output budget — adapters treat
# a budget-exhausted completion as a failed attempt (silent-truncation guard),
# so large quotas would fail or template-ize entire segments. ≤3 personas per
# request keeps ~1200 tokens/persona available under the 4000 ceiling.
_MAX_PERSONAS_PER_REQUEST = 3

# Claim groups that carry per-claim provenance classes (the research-critical
# ones); other list fields stay plain strings.
_CLASSED_GROUPS = ("goals", "needs", "pain_points")


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
    name: str
    archetype: str
    tagline: str = "The Grounded Synthetic User"
    country_code: str = "BD"
    origin_country: str = "Bangladesh"
    demographics: dict[str, Any]
    bio: str
    quote: str
    personality: dict[str, int] = Field(default_factory=lambda: {
        "openness": 50,
        "conscientiousness": 50,
        "extroversion": 50,
        "agreeableness": 50,
        "neuroticism": 50,
    })
    detailed_attributes: dict[str, Any] = Field(default_factory=dict)
    domain_attributes: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    goals: list[str]
    needs: list[str]
    pain_points: list[str]
    behaviors: list[str]
    preferences: list[str]
    motivations: list[str]
    objections: list[str]
    commercial_profile: dict[str, Any]
    technology_profile: dict[str, Any]
    evidence_citations: list[dict[str, Any]] = Field(default_factory=list)
    dataset_refs: list[dict[str, Any]] = Field(default_factory=list)
    # Honest-by-default: scores are earned by validation, never assumed.
    grounding_score: float = 0.0
    confidence: float = 0.0
    status: str = "ready"
    validation_warnings: list[str] = Field(default_factory=list)
    # The ACTUAL origin: "provider/model" from provenance for LLM drafts,
    # TEMPLATE_FALLBACK_MODEL for deterministic ones. Never a fabricated label.
    generation_model: Optional[str] = None


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


def detect_study_domain(study_context: dict[str, Any]) -> str:
    """Intelligently determine business domain from study title, prompt, and audience."""
    blob = (
        str(study_context.get("title", "")) + " "
        + str(study_context.get("prompt", "")) + " "
        + str(study_context.get("target_audience", "")) + " "
        + str(study_context.get("pricing_hypothesis", ""))
    ).lower()

    if any(w in blob for w in ["food", "delivery", "meal", "canteen", "restaurant", "dining", "lunch", "dinner", "hospital worker", "snack"]):
        return "food_delivery"
    if any(w in blob for w in ["saas", "software", "productivity", "workflow", "dashboard", "b2b", "automation", "notion", "spreadsheet", "project management"]):
        return "saas_productivity"
    if any(w in blob for w in ["fitness", "workout", "gym", "exercise", "health", "diet", "nutrition", "training", "wellness"]):
        return "fitness_health"
    if any(w in blob for w in ["exam", "student", "study", "prep", "university", "course", "learning", "tutor", "education", "edtech", "syllabus"]):
        return "edtech_learning"
    if any(w in blob for w in ["fintech", "payment", "bank", "wallet", "credit", "loan", "investment", "ecommerce", "shopping", "retail", "shop"]):
        return "fintech_ecommerce"
    if any(w in blob for w in ["ride", "transport", "commute", "bike", "car", "taxi", "bus", "metro", "transit", "mobility"]):
        return "mobility_transport"

    return "general"


def generate_domain_specific_profile(
    domain: str,
    median_budget: int,
    index: int,
    currency: str = "BDT",
) -> tuple[dict[str, Any], dict[str, Any], list[str], list[str], list[str]]:
    """Produce business-specific domain attributes, explicit constraints, and tailored goals/needs/pains."""
    if domain == "food_delivery":
        domain_attrs = {
            "food_source": "Mostly home-cooked; hospital canteen/nearby stalls when shifts overrun; occasional delivery",
            "meal_timing": "Main meal before shift, snack near 11 PM, tea around 3 AM, breakfast after shift",
            "payment_method": "bKash for mobile payments with cash backup",
            "delivery_frequency": "1–3 times per week during urgent shifts or late hours",
            "preferred_cuisine": "Bangladeshi home-style meals, khichuri, light snacks, milk tea",
            "delivery_concerns": ["Late delivery during night hours", "Food hygiene and packaging safety", "Unpredictable delivery surge fees"],
            "ordering_channel": "Smartphone mobile app / messaging with instant status tracking",
            "price_sensitivity": "High (under ৳150–250 per meal)",
        }
        domain_goals = [
            "Access reliable, hygienic late-night food during unexpected overtime shifts",
            "Keep daily meal expenditure strictly within monthly allowance limits",
            "Avoid disruptions caused by irregular canteen hours",
        ]
        domain_needs = [
            f"Predictable pricing aligned with ৳{median_budget}/month food budget",
            "Guaranteed delivery punctuality during late-night hours with real-time ETA",
            "Instant bKash/Nagad payment confirmation with zero hidden charges",
        ]
        domain_pains = [
            "Canteen closing unexpectedly during emergency late shifts",
            "Cold or stale food delivered after long waiting times",
            "High minimum order limits and surge pricing on standard food delivery apps",
        ]

    elif domain == "saas_productivity":
        domain_attrs = {
            "current_tools": ["Google Sheets", "Notion", "WhatsApp Business", "bKash merchant"],
            "workflow": "Manual spreadsheet data entry with daily evening reconciliation",
            "subscription_behavior": "Low to Moderate tolerance; strictly prefers monthly billing over annual commitments",
            "productivity_problems": ["Data scattered across chat and disconnected sheets", "Manual invoice reconciliation errors"],
            "switching_barrier": "Learning curve for non-technical team members and fear of vendor lock-in",
            "desired_features": ["Automated bKash payment matching", "One-click Bengali invoice generation", "Offline mobile backup"],
            "tech_familiarity": "Moderate to High",
            "decision_style": "Comparative trial with team before committing",
        }
        domain_goals = [
            "Automate repetitive manual spreadsheet tracking and client invoicing",
            "Eliminate reconciliation discrepancies without buying expensive enterprise software",
            f"Keep software subscriptions under ৳{median_budget}/month",
        ]
        domain_needs = [
            "Seamless integration with local payment gateways (bKash/Nagad)",
            "Simple, clutter-free dashboard that works smoothly on mobile and desktop",
            "Transparent pricing without seat-based surprise rate hikes",
        ]
        domain_pains = [
            "Complex Western SaaS products requiring international credit cards",
            "Over-engineered software with bloated features that slow down daily workflow",
            "Lack of responsive local customer support when payment sync fails",
        ]

    elif domain == "fitness_health":
        domain_attrs = {
            "exercise_habits": "Home bodyweight workouts, brisk morning walks, and weekend badminton",
            "fitness_goals": ["Build consistent stamina", "Improve posture after long desk hours", "Maintain healthy weight"],
            "workout_frequency": "3–4 times per week (30–45 minutes per session)",
            "current_fitness_solution": "YouTube workout videos and basic mobile step tracker",
            "spending_behavior": "Resistant to expensive annual gym contracts; open to affordable micro-guidance",
            "health_preferences": "Home-based low-equipment routines with realistic local dietary tips",
            "schedule_fit": "Early morning before work (6:30 AM) or evening (8:00 PM)",
            "barriers": ["Unpredictable overtime work schedule", "Lack of personalized progress tracking"],
        }
        domain_goals = [
            "Maintain an active physical routine despite a demanding work schedule",
            "Receive practical workout routines that require zero expensive gym equipment",
            f"Track measurable health progress without spending over ৳{median_budget}/month",
        ]
        domain_needs = [
            "Short, high-efficiency workout sessions that fit into 30-minute windows",
            "Nutrition suggestions based on easily available Bangladeshi foods",
            "Gentle habit reminders that don't cause notification fatigue",
        ]
        domain_pains = [
            "Expensive gym memberships with long commutes through heavy traffic",
            "Generic Western diet plans recommending costly, inaccessible ingredients",
            "Losing motivation when work deadlines interrupt exercise consistency",
        ]

    elif domain == "edtech_learning":
        domain_attrs = {
            "study_schedule": "Evening study blocks (7:00 PM – 11:30 PM) plus weekend review sessions",
            "learning_style": "Video lessons paired with timed practice quizzes and past exam papers",
            "current_study_tools": ["YouTube playlists", "Shared Google Drive batch folders", "Telegram study groups"],
            "exam_priorities": ["University semester finals", "Competitive job recruitment exams (BCS / Bank jobs)"],
            "monthly_education_budget": f"৳{median_budget} BDT",
            "device_access": "Android smartphone and shared family laptop",
            "switching_barrier": "Skepticism toward unverified question banks without verified answer keys",
        }
        domain_goals = [
            "Master difficult syllabus topics efficiently within limited preparation time",
            "Access high-quality mock tests and structured topic summaries",
            f"Keep monthly educational tool expenses strictly within ৳{median_budget} BDT",
        ]
        domain_needs = [
            "Clear, concise video explanations in Bangla with chapter markers",
            "Offline downloadable study notes for studying during power outages or commutes",
            "Instant doubt clearance and step-by-step math/logic explanations",
        ]
        domain_pains = [
            "Expensive coaching centers with rigid schedules and high commute time",
            "Pirated, disorganized study materials with incorrect answer keys",
            "Slow mobile internet causing buffering on live lecture streams",
        ]

    else:  # General / Fintech / E-commerce
        domain_attrs = {
            "primary_channel": "Mobile-first digital app and messaging",
            "payment_preference": "bKash / Nagad Mobile Wallet",
            "shopping_frequency": "Bi-weekly or monthly as needed",
            "adoption_barrier": "Trust in product quality, return policy, and reliable delivery",
            "price_sensitivity": "High to Moderate",
            "decision_style": "Comparative research based on peer reviews and transparent pricing",
        }
        domain_goals = [
            "Reduce friction in daily commercial and service transactions",
            "Ensure financial security and transparent pricing on all digital platforms",
            f"Maintain monthly expenditure within ৳{median_budget} budget limits",
        ]
        domain_needs = [
            "Fast, reliable mobile service with instant payment confirmation",
            "Honest, transparent terms with no hidden platform fees",
            "Responsive customer support via chat or hotline",
        ]
        domain_pains = [
            "Unreliable service execution and difficult refund processes",
            "Platforms that require international payment cards instead of local MFS",
            "Aggressive spam notifications and non-transparent pricing surges",
        ]

    # Explicit Behavioral & Financial Constraints
    constraints = {
        "max_monthly_budget": median_budget,
        "max_transaction_bdt": int(median_budget * 0.45),
        "subscription_tolerance": "Low" if median_budget <= 500 else "Moderate",
        "time_tolerance": "Low (requires under 10 minutes to complete tasks)",
        "technology_tolerance": "Medium",
        "switching_tolerance": "Low (requires verified peer proof before switching)",
        "preferred_payment_method": domain_attrs.get("payment_method", "bKash Mobile Wallet"),
        "price_sensitivity": "High" if median_budget <= 500 else "Moderate",
        "risk_tolerance": "Low to Moderate",
    }

    return domain_attrs, constraints, domain_goals, domain_needs, domain_pains


_RICH_ARCHETYPE_TEMPLATES = [
    {
        "name": "Nusrat Jahan",
        "gender": "Female",
        "age": 31,
        "occupation": "Night Shift Worker",
        "location": "Dhaka, Bangladesh",
        "country_code": "BD",
        "origin_country": "Bangladesh",
        "tagline": "The Steady Night Caregiver",
        "bio": (
            "She works rotating overnight shifts at a private hospital and depends on routines to get through long, "
            "demanding nights. She usually brings food from home, but when emergencies stretch her shift, she wants a "
            "late-night option that is safe, predictable, and worth the money."
        ),
        "quote": "When my shift runs past 3 am, I need something reliable and budget-conscious without guessing.",
        "personality": {
            "openness": 44,
            "conscientiousness": 86,
            "extroversion": 50,
            "agreeableness": 76,
            "neuroticism": 58,
        },
        "detailed_attributes": {
            "hobbies": "watching Bangla dramas, tending balcony plants, and listening to health podcasts",
            "origin_country": "Bangladesh",
            "commute_mode": "rickshaw for local travel and occasional staff transport after late shifts",
            "food_source": "mostly home-cooked meals; hospital canteen or nearby stalls when shifts overrun; occasional delivery if it seems reliable",
            "meal_timing": "main meal before shift, light snack around 11 pm, tea near 3 am, breakfast after returning home",
            "payment_method": "bKash for most transactions, with cash as a backup",
            "work_schedule": "rotating night shifts, usually 8 pm to 8 am, 4 nights a week",
            "workplace_setting": "private hospital ward",
            "activity_level": "moderately active because she spends long hours on her feet",
            "adaptability_level": "moderate",
            "anxiety_level": "moderately high when plans change suddenly or services fail late at night",
            "attention_focus": "task-focused with strong awareness of timing and practical details",
            "belief_system": "practical, duty-centered, and moderately religious",
            "communication_style": "polite, concise, and direct under time pressure",
            "community_engagement": "keeps light ties with neighbors and relatives but has limited time for events",
            "coping_strategies": "tea breaks, prayer, short calls home, and sticking to checklists",
            "core_motivators": "doing her job well, protecting her income, and keeping household life manageable",
            "cultural_affiliations": "urban Bangladeshi middle-class culture",
            "cultural_traditions": "values family meals on off days, Eid gatherings, and deference to elders",
            "daily_activities": "patient care, charting, commuting, family check-ins, and recovering sleep",
            "decision_style": "deliberate and pragmatic",
            "family_dynamics": "supportive but time-constrained, with shared responsibilities at home",
            "financial_attitude": "careful spender who tracks small expenses closely",
            "financial_profile": "lower-middle to middle-income salaried household with tight monthly margins",
            "general_risk": "low to moderate",
            "growth_mindset": "willing to improve through structured training and practical feedback",
            "household_structure": "multigenerational family household",
            "introversion_level": "moderately introverted",
            "language_preferences": "Bangla first; comfortable with basic English at work",
            "learning_style": "learns best through demonstration and repeated use",
            "life_priorities": "family wellbeing, steady work, and enough rest to function",
            "motivation_goals": "maintain stability, reduce daily friction, and build a slightly better routine over time",
            "personal_independence": "self-reliant in everyday matters but consults family on major decisions",
            "personal_values": "stability, responsibility, and caring for family",
            "planning_horizon": "mostly week-to-week with monthly budgeting goals",
            "religious_practices": "observes daily prayers when schedule allows and follows major Islamic holidays",
            "schedule_flexibility": "low because emergency cases and rota changes can override personal plans",
            "self_discipline": "strong",
            "sleep_schedule": "fragmented daytime sleep after night duty",
            "social_identity": "a working woman balancing professional duty and family expectations",
            "social_values": "respect, modesty, reliability, and consideration for others",
            "spiritual_outlook": "finds comfort in faith, routine, and gratitude",
            "tech_interest": "functional rather than enthusiastic",
            "technology_usage": "heavy smartphone use for messaging, mobile payments, maps, and shift coordination",
            "time_management": "structured but often disrupted by urgent work demands",
            "urban_living": "accustomed to congestion and delays, values services that save time",
            "value_risk": "prefers proven options and avoids unnecessary experimentation",
            "work_ethic": "highly dependable and methodical",
        },
    },
    {
        "name": "Tanvir Ahmed",
        "gender": "Male",
        "age": 28,
        "occupation": "Fintech Operations Analyst",
        "location": "Dhaka, Bangladesh",
        "country_code": "BD",
        "origin_country": "Bangladesh",
        "tagline": "The Pragmatic Efficiency Optimizer",
        "bio": (
            "Tanvir oversees payment settlements and reconciliation workflows. He relies on structured spreadsheet "
            "automation and digital banking apps to maintain financial discipline and support his growing household."
        ),
        "quote": "If a platform cannot guarantee seamless mobile payment settlement with zero hidden deductions, I will not adopt it.",
        "personality": {
            "openness": 62,
            "conscientiousness": 90,
            "extroversion": 58,
            "agreeableness": 70,
            "neuroticism": 42,
        },
        "detailed_attributes": {
            "hobbies": "following cricket leagues, testing new fintech apps, and casual weekend badminton",
            "origin_country": "Bangladesh",
            "commute_mode": "ride-sharing bike or metro rail during peak rush hours",
            "food_source": "office catering during lunch; family dinners prepared at home",
            "meal_timing": "quick breakfast at 8 am, lunch at 1:30 pm, evening tea at 6 pm, dinner at 9:30 pm",
            "payment_method": "bKash, Nagad, and local debit card",
            "work_schedule": "Sunday to Thursday, 9 am to 6 pm with occasional month-end audits",
            "workplace_setting": "corporate shared office space in Motijheel/Gulshan",
            "activity_level": "moderate desk-bound workflow with active commuting",
            "adaptability_level": "high with digital tools and structured protocols",
            "anxiety_level": "low to moderate, triggered primarily by system reconciliation lags",
            "attention_focus": "analytical, metric-oriented, and detail-vigilant",
            "belief_system": "pragmatic, forward-looking, and socially responsible",
            "communication_style": "structured, data-grounded, and concise",
            "community_engagement": "active in professional alumni groups and neighborhood sports clubs",
            "coping_strategies": "structured task tracking, evening runs, and weekend family outings",
            "core_motivators": "career advancement, financial independence, and optimizing monthly savings",
            "cultural_affiliations": "urban young professional culture",
            "cultural_traditions": "family dinner gatherings, Eid celebrations, and supporting younger siblings",
            "daily_activities": "data reporting, vendor coordination, commuting, and budgeting",
            "decision_style": "comparative and data-driven",
            "family_dynamics": "close-knit nuclear family contributing to parents' monthly expenses",
            "financial_attitude": "systematic saver with automated monthly deposits",
            "financial_profile": "salaried middle-income with growing discretionary headroom",
            "general_risk": "moderate, analytical approach to new investments",
            "growth_mindset": "proactively learns business intelligence and workflow automation",
            "household_structure": "married couple sharing household budgeting",
            "introversion_level": "balanced ambivert",
            "language_preferences": "bilingual in Bangla and professional English",
            "learning_style": "hands-on trial, documentation reviews, and product walkthroughs",
            "life_priorities": "career progression, owning an apartment, and family security",
            "motivation_goals": "streamline daily operational friction and maximize investment yield",
            "personal_independence": "high autonomy in daily and financial choices",
            "personal_values": "transparency, punctuality, and professional excellence",
            "planning_horizon": "quarterly milestones with 3-year financial forecasts",
            "religious_practices": "attends Friday congregational prayers and observes Ramadan",
            "schedule_flexibility": "moderate on weekdays; values protected weekends",
            "self_discipline": "very high",
            "sleep_schedule": "consistent 11:30 pm to 6:30 am sleep pattern",
            "social_identity": "modern Bangladeshi tech-enabled professional",
            "social_values": "integrity, mutual respect, and meritocracy",
            "spiritual_outlook": "grounded faith balanced with empirical thinking",
            "tech_interest": "high enthusiasm for fintech, productivity tools, and AI utilities",
            "technology_usage": "dual-monitor workstation, flagship Android smartphone, multiple payment apps",
            "time_management": "rigorous calendar scheduling and batch processing",
            "urban_living": "navigates Dhaka traffic using real-time route navigation apps",
            "value_risk": "calculates ROI before committing to any paid service",
            "work_ethic": "results-driven, proactive, and process-oriented",
        },
    },
    {
        "name": "Sadia Islam",
        "gender": "Female",
        "age": 22,
        "occupation": "Undergraduate Student & Freelance Designer",
        "location": "Dhaka, Bangladesh",
        "country_code": "BD",
        "origin_country": "Bangladesh",
        "tagline": "The Ambitious Mobile Multi-Tasker",
        "bio": (
            "Sadia balances her final-year university coursework with freelance UI design gigs. "
            "She operates primarily on a student budget and looks for agile, mobile-first micro-subscriptions."
        ),
        "quote": "I want tools that give me premium output without requiring a corporate budget or international credit card.",
        "personality": {
            "openness": 78,
            "conscientiousness": 74,
            "extroversion": 64,
            "agreeableness": 80,
            "neuroticism": 48,
        },
        "detailed_attributes": {
            "hobbies": "digital illustration, exploring aesthetic cafes, and creating design tutorials",
            "origin_country": "Bangladesh",
            "commute_mode": "university bus and rickshaw",
            "food_source": "campus cafeteria, home-cooked food, and street snacks with friends",
            "meal_timing": "late breakfast, campus lunch at 2 pm, tea snacks at 6 pm, late dinner at 10 pm",
            "payment_method": "bKash and student bank account",
            "work_schedule": "flexible class hours with late evening freelance design work",
            "workplace_setting": "university campus and home study desk",
            "activity_level": "moderate with frequent campus walking",
            "adaptability_level": "very high with digital platforms and new creative workflows",
            "anxiety_level": "moderate during assignment submission and client deadline weeks",
            "attention_focus": "creative, visual, and deadline-driven",
            "belief_system": "progressive, collaborative, and expressive",
            "communication_style": "expressive, visual, and fast-paced messaging",
            "community_engagement": "active in student design clubs and online creative communities",
            "coping_strategies": "listening to lo-fi music, sketching, and chatting with university peers",
            "core_motivators": "building a standout portfolio and achieving financial self-sufficiency",
            "cultural_affiliations": "youth creative and academic culture in Dhaka",
            "cultural_traditions": "Pahela Baishakh festivities, university cultural fairs, and family Eid",
            "daily_activities": "attending lectures, client revisions, group projects, and social media",
            "decision_style": "intuitive and visually informed",
            "family_dynamics": "living with parents who encourage her education and creative pursuits",
            "financial_attitude": "budget-conscious student managing freelance earnings carefully",
            "financial_profile": "student with supplemental freelance income (tight discretionary limit)",
            "general_risk": "moderate to high for creative experiments, low for financial commitments",
            "growth_mindset": "constantly upskilling through online courses and peer feedback",
            "household_structure": "student living in family home",
            "introversion_level": "outgoing and collaborative",
            "language_preferences": "Bangla and English mixed naturally (Banglish in casual communication)",
            "learning_style": "video tutorials, interactive experiments, and trial-and-error",
            "life_priorities": "graduating with honors, landing design clients, and personal freedom",
            "motivation_goals": "reduce design turnaround time and build automated passive income",
            "personal_independence": "growing financial independence through remote design work",
            "personal_values": "creativity, authenticity, and empathy",
            "planning_horizon": "weekly academic syllabus and monthly project deliveries",
            "religious_practices": "observes major religious and cultural occasions with family",
            "schedule_flexibility": "high flexibility between classes, tight during final exams",
            "self_discipline": "strong when engaged in passion projects",
            "sleep_schedule": "late night owl (1 am to 8 am)",
            "social_identity": "creative digital native and ambitious student",
            "social_values": "diversity, peer encouragement, and ethical consumption",
            "spiritual_outlook": "open-minded and reflective",
            "tech_interest": "high; early adopter of creative AI and design software",
            "technology_usage": "iPad with stylus, MacBook, Android smartphone, heavy Figma and Canva user",
            "time_management": "deadline-driven with flexible creative bursts",
            "urban_living": "relies on food and grocery delivery apps for convenience during project crunches",
            "value_risk": "hesitant to enter recurring long-term annual contracts",
            "work_ethic": "passionate, energetic, and adaptable under creative deadlines",
        },
    },
]


def _generate_deterministic_persona_fallback(
    segment: Any,
    index: int,
    study_context: dict[str, Any],
    evidence_claims: list[Any],
) -> GeneratedPersonaDraft:
    """Generate a high-fidelity synthetic persona matching the rich 45+ attribute specification and dynamic domain."""
    template = _RICH_ARCHETYPE_TEMPLATES[index % len(_RICH_ARCHETYPE_TEMPLATES)]
    seg_name = getattr(segment, "name", "Target User")
    seg_char = getattr(segment, "characteristics", {}) or {}
    econ = seg_char.get("economics", {}).get("monthly_budget", {}) or {}
    demo = seg_char.get("demographics", {}) or {}
    behav = seg_char.get("behavior", {}) or {}

    domain = detect_study_domain(study_context)
    name = template["name"]
    tagline = template.get("tagline", f"The Grounded {seg_name} Representative")
    country_code = template.get("country_code", "BD")
    origin_country = template.get("origin_country", "Bangladesh")

    age_range = demo.get("age_range")
    if age_range and len(age_range) == 2:
        min_a, max_a = int(age_range[0]), int(age_range[1])
        tpl_age = template.get("age", 25)
        if min_a <= tpl_age <= max_a:
            age = tpl_age
        else:
            age = min_a + ((tpl_age + index) % (max_a - min_a + 1))
    else:
        age = template.get("age", 25)

    occupation = demo.get("dominant_occupation") or template.get("occupation", "Professional")
    location = demo.get("location") or template.get("location", "Dhaka, Bangladesh")

    median_budget = int(econ.get("median", 450))
    budget_range = f"৳{econ.get('min', 250)}–৳{econ.get('max', 750)}"
    currency = econ.get("currency", "BDT")

    # Domain-adapted attributes, constraints, goals, needs, and pain points
    domain_attrs, constraints, dom_goals, dom_needs, dom_pains = generate_domain_specific_profile(
        domain, median_budget, index, currency
    )

    # Template drafts cite nothing — every claim below is SYNTHETIC, so the
    # citations list is honestly empty instead of decorating with claims[:3].
    matched_citations: list[dict[str, Any]] = []

    bio = template.get("bio", f"{name} is a {age}-year-old {occupation.lower()} based in {location}.")
    quote = template.get("quote", f"I need an intelligent tool that keeps my priorities on track within my ৳{median_budget}/month budget.")

    personality = dict(template.get("personality", {
        "openness": 50,
        "conscientiousness": 50,
        "extroversion": 50,
        "agreeableness": 50,
        "neuroticism": 50,
    }))

    detailed_attributes = dict(template.get("detailed_attributes", {}))
    # Inject domain attributes into detailed attributes
    detailed_attributes["domain_attributes"] = domain_attrs
    detailed_attributes["constraints"] = constraints
    for k, v in domain_attrs.items():
        if isinstance(v, (str, int, float, list)):
            detailed_attributes[k] = v

    goals = dom_goals or [
        "Maintain stability and predictability across demanding daily routines",
        "Reduce operational friction and avoid unverified services",
        "Protect monthly household budget through reliable spending choices",
    ]

    needs = seg_char.get("needs") or dom_needs or [
        f"Predictable pricing aligned with {currency} {median_budget}/mo budget",
        "Seamless mobile access with low-bandwidth optimization and offline backup",
    ]

    pain_points = dom_pains or [
        "Unpredictable service disruptions during late hours or urgent deadlines",
        "Fragmented tools requiring complex payment setup without mobile wallet support",
        "Hesitation with unverified platforms that overpromise and underdeliver",
    ]

    behaviors = [
        f"Spends active hours balancing professional tasks with personal duties",
        f"Prefers instant mobile wallet ({constraints.get('preferred_payment_method', 'bKash')}) confirmation for every purchase",
        "Relies on established peer recommendations before trying new digital services",
    ]

    preferences = [
        "Clear, clutter-free mobile interface with fast status feedback",
        "Transparent pricing with no surprise recurring billing deductions",
    ]

    motivations = [
        "Doing daily work well while protecting personal and family wellbeing",
        "Saving time on repetitive daily friction points",
    ]

    objections = [
        "Skeptical of complex setups requiring long-term upfront lock-in",
        "Rejects apps that fail to work reliably in low-connectivity urban zones",
    ]

    commercial_profile = {
        "monthly_budget_bdt": median_budget,
        "budget_range": budget_range,
        "price_sensitivity": "High" if median_budget <= 500 else "Moderate",
        "payment_preference": constraints.get("preferred_payment_method", "bKash / Nagad Mobile Wallet"),
        "willingness_to_pay": f"{currency} {econ.get('min', 250)}–{econ.get('max', 750)} / month",
        "constraints": constraints,
    }

    technology_profile = {
        "primary_devices": ["Android Smartphone", "Laptop"] if index % 2 == 0 else ["Android Smartphone"],
        "platforms": ["WhatsApp", "Facebook Messenger", "bKash"],
        "familiarity": behav.get("technology_familiarity", "Medium"),
    }

    dataset_refs = [
        {"variable": "monthly_budget", "value": median_budget, "source": "Empirical Segment Profile"},
        {"variable": "age", "value": age, "source": "Empirical Segment Profile"},
    ]

    # Templates invent every claim — label them honestly.
    detailed_attributes["claim_provenance"] = {
        group: [{"value": v, "provenance": "SYNTHETIC", "evidence_ids": []} for v in vals]
        for group, vals in (("goals", goals), ("needs", needs), ("pain_points", pain_points))
    }

    validation = validate_synthetic_persona(
        {
            "name": name,
            "demographics": {"age": age, "occupation": occupation, "location": location},
            "goals": goals,
            "needs": needs,
            "pain_points": pain_points,
            "behaviors": behaviors,
            "commercial_profile": commercial_profile,
            "evidence_citations": matched_citations,
            "claim_provenance": detailed_attributes["claim_provenance"],
        },
        seg_char,
        evidence_claims,
    )

    return GeneratedPersonaDraft(
        name=name,
        archetype=template.get("occupation", f"{seg_name} Archetype"),
        tagline=tagline,
        country_code=country_code,
        origin_country=origin_country,
        demographics={
            "age": age,
            "occupation": occupation,
            "location": location,
            "education": "Graduate / Professional",
            "income_or_budget": f"{currency} {median_budget}/mo",
        },
        bio=bio,
        quote=quote,
        personality=personality,
        detailed_attributes=detailed_attributes,
        domain_attributes=domain_attrs,
        constraints=constraints,
        goals=goals,
        needs=needs,
        pain_points=pain_points,
        behaviors=behaviors,
        preferences=preferences,
        motivations=motivations,
        objections=objections,
        commercial_profile=commercial_profile,
        technology_profile=technology_profile,
        evidence_citations=matched_citations,
        dataset_refs=dataset_refs,
        grounding_score=validation.grounding_score,
        confidence=validation.confidence,
        status=validation.status,
        validation_warnings=validation.warnings,
        generation_model=TEMPLATE_FALLBACK_MODEL,
    )


async def generate_personas_for_study(
    study: Any,
    segments: list[Any],
    target_count: int = 6,
    distribution_strategy: str = "population_weighted",
    datasets: list[Any] | None = None,
    evidence_claims: list[Any] | None = None,
    llm_service: Optional[LLMService] = None,
) -> list[GeneratedPersonaDraft]:
    """Generate grounded synthetic customer personas across study segments with full personality, lifestyle, domain attributes, and explicit constraints."""
    if not segments:
        raise ValueError("Cannot generate personas: study has no market segments. Run segmentation first.")

    quotas = calculate_segment_quotas(segments, target_count, distribution_strategy)
    claims = evidence_claims or []
    study_ctx = {
        "title": getattr(study, "title", "Product Study"),
        "prompt": getattr(study, "prompt", ""),
        "target_audience": getattr(study, "target_audience", "Target Consumers"),
        "pricing_hypothesis": getattr(study, "pricing_hypothesis", "Market pricing"),
    }
    detected_domain = detect_study_domain(study_ctx)

    all_generated: list[GeneratedPersonaDraft] = []
    global_idx = 0

    for seg in segments:
        seg_id = getattr(seg, "id", "")
        count_for_seg = quotas.get(seg_id, 1)
        seg_char = getattr(seg, "characteristics", {}) or {}
        seg_name = getattr(seg, "name", "Segment")

        if not llm_service:
            for i in range(count_for_seg):
                draft = _generate_deterministic_persona_fallback(seg, global_idx, study_ctx, claims)
                all_generated.append(draft)
                global_idx += 1
            continue

        # LLM-assisted generation — in sub-batches (see _MAX_PERSONAS_PER_REQUEST)
        base_payload = {
            "study_context": study_ctx,
            "detected_domain": detected_domain,
            "segment": {
                "name": seg_name,
                "cluster_label": getattr(seg, "cluster_label", "cluster_0"),
                "population_percentage": getattr(seg, "population_percentage", 35.0),
                "characteristics": seg_char,
            },
            "evidence_claims": [
                {"id": f"C{i + 1}", "text": getattr(c, "claim_text", ""), "category": getattr(c, "category", "general")}
                for i, c in enumerate(claims[:6])
            ],
        }
        # Alias → real evidence id, so stored citations resolve after generation.
        # Claims without a real id keep the alias rather than losing the link.
        claim_id_map = {
            f"C{i + 1}": (getattr(c, "id", "") or f"C{i + 1}") for i, c in enumerate(claims[:6])
        }

        system_prompt = (
            "You are BebshaX's synthetic customer persona synthesis engine. Generate realistic, data-grounded "
            "synthetic personas strictly matching the provided market segment characteristics, business domain, and evidence findings.\n"
            "Rules:\n"
            "1. Output valid JSON with key 'personas' containing an array of persona objects.\n"
            "2. Each persona must include:\n"
            "   - name, age, occupation, location, country_code (e.g. 'BD'), tagline (e.g. 'The Steady Night Caregiver'), bio (2-3 sentences), quote (1 sentence)\n"
            "   - personality: object with integer scores (0-100) for openness, conscientiousness, extroversion, agreeableness, neuroticism\n"
            "   - domain_attributes: object tailored to the business domain (e.g. food delivery: food_source, meal_timing, delivery_frequency, delivery_concerns; SaaS: current_tools, workflow, switching_barrier, desired_features; fitness: exercise_habits, fitness_goals, workout_frequency)\n"
            "   - constraints: object with max_monthly_budget, subscription_tolerance, switching_tolerance, preferred_payment_method, price_sensitivity\n"
            "   - detailed_attributes: object with hobbies, commute_mode, work_schedule, communication_style, coping_strategies, daily_activities, decision_style, financial_attitude, tech_interest, technology_usage, time_management\n"
            "   - goals, needs, pain_points: arrays of claim objects {\"value\": str, \"provenance\": \"OBSERVED\"|\"INFERRED\"|\"SYNTHETIC\", \"evidence_ids\": [claim ids like \"C1\"]}.\n"
            "     Provenance rules (citations are checked against the provided claim ids): OBSERVED only when directly supported by a provided evidence claim — cite its id(s); "
            "INFERRED when reasonably deduced from segment/domain context; SYNTHETIC for plausible invention. Never fabricate ids.\n"
            "   - behaviors, preferences, motivations, objections (arrays of strings)\n"
            "   - monthly_budget_bdt (number), price_sensitivity, primary_devices (array), platforms (array), tech_familiarity\n"
            "3. Ages and budgets must strictly fall within the segment's specified bounds.\n"
            "4. Ground every persona authentically in their regional lifestyle, domain behavior, and practical daily reality."
        )

        raw_personas: list[tuple[dict, str]] = []  # (persona dict, serving provider/model)
        template_fill = 0  # personas owed by failed/empty batches — filled honestly below
        remaining = count_for_seg
        while remaining > 0:
            batch_count = min(remaining, _MAX_PERSONAS_PER_REQUEST)
            remaining -= batch_count
            request = LLMRequest(
                task=TaskType.PERSONA_GENERATION,
                messages=[
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=json.dumps({**base_payload, "count_to_generate": batch_count})),
                ],
                json_mode=True,
                # 0.75, not 0.3: low temperature makes every segment's personas
                # converge on the same archetype phrasing — diversity is a core
                # quality metric. Structure safety comes from json_mode + the
                # per-field validation below, not from a frozen sampler.
                temperature=0.75,
                # ~1200 tokens covers one persona's full schema with headroom;
                # the adapter raises on budget-exhausted completions.
                max_output_tokens=min(1200 * batch_count, 4000),
            )
            try:
                result = await llm_service.complete(request)
                served_by = (
                    f"{result.provenance.served_by_provider}/{result.provenance.served_by_model}"
                    if result.provenance.served_by_provider
                    else "llm/unknown"
                )
                cleaned = re.sub(r"^```(?:json)?\s*", "", result.text.strip())
                cleaned = re.sub(r"\s*```$", "", cleaned)
                parsed = json.loads(cleaned)
                batch_personas = parsed.get("personas", []) if isinstance(parsed, dict) else []
                if batch_personas:
                    # pair each draft with ITS batch's serving model — pool
                    # failover mid-segment must not misattribute earlier batches
                    raw_personas.extend((p, served_by) for p in batch_personas[:batch_count])
                else:
                    logger.warning(
                        "persona generation returned no personas for segment %s — "
                        "filling batch with labeled templates",
                        seg_name,
                    )
                    template_fill += batch_count
            except (AllCandidatesFailed, ContextWindowExceeded):
                # Honest infrastructure failure — never quietly replaced with
                # template personas pretending to be research output (R2/R6).
                raise
            except Exception:
                logger.warning(
                    "persona generation failed for segment %s — filling batch with labeled templates",
                    seg_name,
                    exc_info=True,
                )
                template_fill += batch_count

        for p_raw, served_by in raw_personas[: count_for_seg - template_fill]:
                fallback_draft = _generate_deterministic_persona_fallback(seg, global_idx, study_ctx, claims)
                fallback_template = _RICH_ARCHETYPE_TEMPLATES[global_idx % len(_RICH_ARCHETYPE_TEMPLATES)]
                name = p_raw.get("name") or fallback_template["name"]
                age = int(p_raw.get("age", fallback_template.get("age", 25)))
                occupation = p_raw.get("occupation", fallback_template.get("occupation", "Professional"))
                location = p_raw.get("location", fallback_template.get("location", "Dhaka, Bangladesh"))
                tagline = p_raw.get("tagline") or fallback_template.get("tagline", f"The Grounded {seg_name} Representative")
                country_code = p_raw.get("country_code") or fallback_template.get("country_code", "BD")
                origin_country = p_raw.get("origin_country") or fallback_template.get("origin_country", "Bangladesh")
                budget_num = int(p_raw.get("monthly_budget_bdt", fallback_draft.commercial_profile.get("monthly_budget_bdt", 450)))

                personality_raw = p_raw.get("personality", {})
                personality = {
                    "openness": int(personality_raw.get("openness", fallback_template["personality"]["openness"])),
                    "conscientiousness": int(personality_raw.get("conscientiousness", fallback_template["personality"]["conscientiousness"])),
                    "extroversion": int(personality_raw.get("extroversion", fallback_template["personality"]["extroversion"])),
                    "agreeableness": int(personality_raw.get("agreeableness", fallback_template["personality"]["agreeableness"])),
                    "neuroticism": int(personality_raw.get("neuroticism", fallback_template["personality"]["neuroticism"])),
                }

                domain_attrs = dict(fallback_draft.domain_attributes)
                if isinstance(p_raw.get("domain_attributes"), dict):
                    for k, v in p_raw["domain_attributes"].items():
                        if v:
                            domain_attrs[k] = v

                constraints = dict(fallback_draft.constraints)
                if isinstance(p_raw.get("constraints"), dict):
                    for k, v in p_raw["constraints"].items():
                        if v:
                            constraints[k] = v
                constraints["max_monthly_budget"] = budget_num

                # Bangladeshi archetype templates only backfill Bangladeshi
                # personas — a US-market persona must not inherit bKash habits.
                is_bd_context = "bangladesh" in str(location).lower() or str(country_code).upper() == "BD"
                detailed_attributes = (
                    dict(fallback_template.get("detailed_attributes", {})) if is_bd_context else {}
                )
                if isinstance(p_raw.get("detailed_attributes"), dict):
                    for k, v in p_raw["detailed_attributes"].items():
                        if v:
                            detailed_attributes[k] = v
                detailed_attributes["domain_attributes"] = domain_attrs
                detailed_attributes["constraints"] = constraints
                for k, v in domain_attrs.items():
                    detailed_attributes[k] = v

                # Per-claim provenance (downgrade-only, citations verified
                # against the claim ids actually shown to the model).
                claim_values: dict[str, list[str]] = {}
                claim_provenance: dict[str, list[dict[str, Any]]] = {}
                for group in _CLASSED_GROUPS:
                    vals, classed = _coerce_claim_list(p_raw.get(group), claim_id_map)
                    if not vals:
                        vals = list(getattr(fallback_draft, group))
                        classed = [
                            {"value": v, "provenance": "SYNTHETIC", "evidence_ids": []} for v in vals
                        ]
                    claim_values[group] = vals
                    claim_provenance[group] = classed
                detailed_attributes["claim_provenance"] = claim_provenance

                # Citations mirror what the persona actually cites — the union
                # of verified evidence_ids across its claims, never claims[:3].
                claim_by_id = {getattr(c, "id", ""): c for c in claims}
                cited_ids = sorted(
                    {
                        eid
                        for group_entries in claim_provenance.values()
                        for entry in group_entries
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

                commercial_prof = {
                    "monthly_budget_bdt": budget_num,
                    "price_sensitivity": p_raw.get("price_sensitivity", "High" if budget_num <= 500 else "Moderate"),
                    "payment_preference": p_raw.get("payment_preference", constraints.get("preferred_payment_method", "bKash Mobile Wallet")),
                    "willingness_to_pay": f"৳{budget_num}/mo",
                    "constraints": constraints,
                }

                validation = validate_synthetic_persona(
                    {
                        "name": name,
                        "demographics": {"age": age, "occupation": occupation, "location": location},
                        "goals": claim_values["goals"],
                        "needs": claim_values["needs"],
                        "pain_points": claim_values["pain_points"],
                        "behaviors": p_raw.get("behaviors", fallback_draft.behaviors),
                        "commercial_profile": commercial_prof,
                        "evidence_citations": matched_citations,
                        "claim_provenance": claim_provenance,
                    },
                    seg_char,
                    claims,
                )

                all_generated.append(
                    GeneratedPersonaDraft(
                        name=name,
                        archetype=occupation or f"{seg_name} Archetype",
                        tagline=tagline,
                        country_code=country_code,
                        origin_country=origin_country,
                        demographics={
                            "age": age,
                            "occupation": occupation,
                            "location": location,
                            "education": p_raw.get("education", "Graduate / Professional"),
                            "income_or_budget": f"৳{budget_num}/mo",
                        },
                        bio=p_raw.get("bio") or f"{name} is a {age}-year-old {occupation} in {location}.",
                        quote=p_raw.get("quote") or "I need a dependable, cost-effective service.",
                        personality=personality,
                        detailed_attributes=detailed_attributes,
                        domain_attributes=domain_attrs,
                        constraints=constraints,
                        goals=claim_values["goals"],
                        needs=claim_values["needs"],
                        pain_points=claim_values["pain_points"],
                        behaviors=p_raw.get("behaviors") or fallback_draft.behaviors,
                        preferences=p_raw.get("preferences") or fallback_draft.preferences,
                        motivations=p_raw.get("motivations") or fallback_draft.motivations,
                        objections=p_raw.get("objections") or fallback_draft.objections,
                        commercial_profile=commercial_prof,
                        technology_profile={
                            "primary_devices": p_raw.get("primary_devices", ["Android Smartphone"]),
                            "platforms": p_raw.get("platforms", ["WhatsApp", "Messenger", "bKash"]),
                            "familiarity": p_raw.get("tech_familiarity", "Medium"),
                        },
                        evidence_citations=matched_citations,
                        dataset_refs=[{"variable": "monthly_budget", "value": budget_num, "source": "Market Segment"}],
                        grounding_score=validation.grounding_score,
                        confidence=validation.confidence,
                        status=validation.status,
                        validation_warnings=validation.warnings,
                        generation_model=served_by,
                    )
                )
                global_idx += 1

        # Personas owed by failed/empty batches — honestly labeled templates.
        for _ in range(min(template_fill, count_for_seg)):
            all_generated.append(_generate_deterministic_persona_fallback(seg, global_idx, study_ctx, claims))
            global_idx += 1

    return all_generated

