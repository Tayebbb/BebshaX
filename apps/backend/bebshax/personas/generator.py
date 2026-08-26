"""Grounded synthetic persona generation engine with quota allocation and fallback."""

from __future__ import annotations

import json
import math
import random
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.personas.validator import validate_synthetic_persona


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
    grounding_score: float = 0.90
    confidence: float = 0.85
    status: str = "ready"
    validation_warnings: list[str] = Field(default_factory=list)


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
    """Generate a high-fidelity synthetic persona matching the rich 45+ attribute specification."""
    template = _RICH_ARCHETYPE_TEMPLATES[index % len(_RICH_ARCHETYPE_TEMPLATES)]
    seg_name = getattr(segment, "name", "Target User")
    seg_char = getattr(segment, "characteristics", {}) or {}
    econ = seg_char.get("economics", {}).get("monthly_budget", {}) or {}
    demo = seg_char.get("demographics", {}) or {}
    behav = seg_char.get("behavior", {}) or {}

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

    # Grounded citations
    matched_citations = []
    for c in evidence_claims[:3]:
        matched_citations.append({
            "claim_id": getattr(c, "id", ""),
            "claim_text": getattr(c, "claim_text", ""),
            "category": getattr(c, "category", "general"),
            "confidence": getattr(c, "confidence", 0.85),
        })

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

    goals = [
        "Maintain stability and predictability across demanding daily routines",
        "Reduce operational friction and avoid unverified services",
        "Protect monthly household budget through reliable spending choices",
    ]

    needs = seg_char.get("needs") or [
        f"Predictable pricing aligned with {currency} {median_budget}/mo budget",
        "Seamless mobile access with low-bandwidth optimization and offline backup",
    ]

    pain_points = [
        "Unpredictable service disruptions during late hours or urgent deadlines",
        "Fragmented tools requiring complex payment setup without mobile wallet support",
        "Hesitation with unverified platforms that overpromise and underdeliver",
    ]

    behaviors = [
        f"Spends active hours balancing professional tasks with personal duties",
        "Prefers instant mobile wallet (bKash/Nagad) confirmation for every purchase",
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
        "payment_preference": detailed_attributes.get("payment_method", "bKash / Nagad Mobile Wallet"),
        "willingness_to_pay": f"{currency} {econ.get('min', 250)}–{econ.get('max', 750)} / month",
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
    """Generate grounded synthetic customer personas across study segments with full personality and lifestyle profiles."""
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

        # LLM-assisted generation
        prompt_payload = {
            "study_context": study_ctx,
            "segment": {
                "name": seg_name,
                "cluster_label": getattr(seg, "cluster_label", "cluster_0"),
                "population_percentage": getattr(seg, "population_percentage", 35.0),
                "characteristics": seg_char,
            },
            "evidence_claims": [
                {"text": getattr(c, "claim_text", ""), "category": getattr(c, "category", "general")}
                for c in claims[:6]
            ],
            "count_to_generate": count_for_seg,
        }

        system_prompt = (
            "You are BebshaX's synthetic customer persona synthesis engine. Generate realistic, data-grounded "
            "synthetic personas strictly matching the provided market segment characteristics and evidence findings.\n"
            "Rules:\n"
            "1. Output valid JSON with key 'personas' containing an array of persona objects.\n"
            "2. Each persona must include:\n"
            "   - name, age, occupation, location, country_code (e.g. 'BD'), tagline (e.g. 'The Steady Night Caregiver'), bio (2-3 sentences), quote (1 sentence)\n"
            "   - personality: object with integer scores (0-100) for openness, conscientiousness, extroversion, agreeableness, neuroticism\n"
            "   - detailed_attributes: object with hobbies, origin_country, commute_mode, food_source, meal_timing, payment_method, work_schedule, workplace_setting, activity_level, adaptability_level, anxiety_level, attention_focus, belief_system, communication_style, community_engagement, coping_strategies, core_motivators, cultural_affiliations, cultural_traditions, daily_activities, decision_style, family_dynamics, financial_attitude, financial_profile, general_risk, growth_mindset, household_structure, introversion_level, language_preferences, learning_style, life_priorities, motivation_goals, personal_independence, personal_values, planning_horizon, religious_practices, schedule_flexibility, self_discipline, sleep_schedule, social_identity, social_values, spiritual_outlook, tech_interest, technology_usage, time_management, urban_living, value_risk, work_ethic\n"
            "   - goals (array of 2-4 items), needs (array), pain_points (array), behaviors (array), preferences (array), motivations (array), objections (array)\n"
            "   - monthly_budget_bdt (number), price_sensitivity, primary_devices (array), platforms (array), tech_familiarity\n"
            "3. Ages and budgets must strictly fall within the segment's specified bounds.\n"
            "4. Ground every persona authentically in their regional lifestyle and practical daily reality."
        )

        request = LLMRequest(
            task=TaskType.PERSONA_GENERATION,
            messages=[
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=json.dumps(prompt_payload)),
            ],
            json_mode=True,
            temperature=0.3,
        )

        try:
            result = await llm_service.complete(request)
            cleaned = re.sub(r"^```(?:json)?\s*", "", result.text.strip())
            cleaned = re.sub(r"\s*```$", "", cleaned)
            parsed = json.loads(cleaned)
            personas_list = parsed.get("personas", []) if isinstance(parsed, dict) else []

            if not personas_list:
                for i in range(count_for_seg):
                    all_generated.append(_generate_deterministic_persona_fallback(seg, global_idx, study_ctx, claims))
                    global_idx += 1
                continue

            for p_raw in personas_list[:count_for_seg]:
                fallback_template = _RICH_ARCHETYPE_TEMPLATES[global_idx % len(_RICH_ARCHETYPE_TEMPLATES)]
                name = p_raw.get("name") or fallback_template["name"]
                age = int(p_raw.get("age", fallback_template.get("age", 25)))
                occupation = p_raw.get("occupation", fallback_template.get("occupation", "Professional"))
                location = p_raw.get("location", fallback_template.get("location", "Dhaka, Bangladesh"))
                tagline = p_raw.get("tagline") or fallback_template.get("tagline", f"The Grounded {seg_name} Representative")
                country_code = p_raw.get("country_code") or fallback_template.get("country_code", "BD")
                origin_country = p_raw.get("origin_country") or fallback_template.get("origin_country", "Bangladesh")
                budget_num = int(p_raw.get("monthly_budget_bdt", 450))

                personality_raw = p_raw.get("personality", {})
                personality = {
                    "openness": int(personality_raw.get("openness", fallback_template["personality"]["openness"])),
                    "conscientiousness": int(personality_raw.get("conscientiousness", fallback_template["personality"]["conscientiousness"])),
                    "extroversion": int(personality_raw.get("extroversion", fallback_template["personality"]["extroversion"])),
                    "agreeableness": int(personality_raw.get("agreeableness", fallback_template["personality"]["agreeableness"])),
                    "neuroticism": int(personality_raw.get("neuroticism", fallback_template["personality"]["neuroticism"])),
                }

                detailed_attributes = dict(fallback_template.get("detailed_attributes", {}))
                if isinstance(p_raw.get("detailed_attributes"), dict):
                    for k, v in p_raw["detailed_attributes"].items():
                        if v:
                            detailed_attributes[k] = v

                matched_citations = []
                for c in claims[:3]:
                    matched_citations.append({
                        "claim_id": getattr(c, "id", ""),
                        "claim_text": getattr(c, "claim_text", ""),
                        "category": getattr(c, "category", "general"),
                        "confidence": getattr(c, "confidence", 0.85),
                    })

                validation = validate_synthetic_persona(
                    {
                        "name": name,
                        "demographics": {"age": age, "occupation": occupation, "location": location},
                        "goals": p_raw.get("goals", ["Stay organized and reliable"]),
                        "needs": p_raw.get("needs", ["Affordable pricing and mobile access"]),
                        "pain_points": p_raw.get("pain_points", ["Service unreliability and hidden fees"]),
                        "behaviors": p_raw.get("behaviors", ["Heavy mobile daily user"]),
                        "commercial_profile": {"monthly_budget_bdt": budget_num},
                        "evidence_citations": matched_citations,
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
                        goals=p_raw.get("goals") or ["Maintain routine stability", "Protect monthly savings"],
                        needs=p_raw.get("needs") or ["Transparent pricing", "Mobile wallet integration"],
                        pain_points=p_raw.get("pain_points") or ["High unexpected fees", "Late service failures"],
                        behaviors=p_raw.get("behaviors") or ["Uses mobile daily for coordination"],
                        preferences=p_raw.get("preferences") or ["Clean distraction-free UI"],
                        motivations=p_raw.get("motivations") or ["Consistency and reliability"],
                        objections=p_raw.get("objections") or ["Hesitant about recurring long-term commitments"],
                        commercial_profile={
                            "monthly_budget_bdt": budget_num,
                            "price_sensitivity": p_raw.get("price_sensitivity", "High"),
                            "payment_preference": p_raw.get("payment_preference", detailed_attributes.get("payment_method", "bKash Mobile Wallet")),
                            "willingness_to_pay": f"৳{budget_num}/mo",
                        },
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
                    )
                )
                global_idx += 1

        except Exception:
            for i in range(count_for_seg):
                all_generated.append(_generate_deterministic_persona_fallback(seg, global_idx, study_ctx, claims))
                global_idx += 1

    return all_generated
