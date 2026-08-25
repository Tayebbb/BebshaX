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
    demographics: dict[str, Any]
    bio: str
    quote: str
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
        # Ensure at least 1 persona per segment if target_count >= len(segments)
        count = max(1 if target_count >= len(segments) else 0, fl)
        quotas[sid] = count
        assigned += count
        remainders.append((sid, share - fl))

    # Adjust difference
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


_BANGLADESHI_NAMES = [
    ("Nadia Rahman", "Female"),
    ("Tanvir Ahmed", "Male"),
    ("Sadia Islam", "Female"),
    ("Farhan Kabir", "Male"),
    ("Tasnim Akter", "Female"),
    ("Samiul Hasan", "Male"),
    ("Nabila Chowdhury", "Female"),
    ("Mahmudul Karim", "Male"),
    ("Afsana Mim", "Female"),
    ("Rifat Al-Mamun", "Male"),
]


def _generate_deterministic_persona_fallback(
    segment: Any,
    index: int,
    study_context: dict[str, Any],
    evidence_claims: list[Any],
) -> GeneratedPersonaDraft:
    """Generate a high-fidelity synthetic persona using deterministic templates bounded by segment."""
    name, gender = _BANGLADESHI_NAMES[index % len(_BANGLADESHI_NAMES)]
    seg_name = getattr(segment, "name", "Target User")
    seg_char = getattr(segment, "characteristics", {}) or {}
    econ = seg_char.get("economics", {}).get("monthly_budget", {}) or {}
    demo = seg_char.get("demographics", {}) or {}
    behav = seg_char.get("behavior", {}) or {}

    age_range = demo.get("age_range", [19, 23])
    min_age = age_range[0] if isinstance(age_range, (list, tuple)) else 19
    max_age = age_range[1] if isinstance(age_range, (list, tuple)) else 23
    age = min_age + (index % (max(1, max_age - min_age + 1)))

    median_budget = int(econ.get("median", 400))
    budget_range = f"৳{econ.get('min', 250)}–৳{econ.get('max', 600)}"
    currency = econ.get("currency", "BDT")

    occupation = demo.get("dominant_occupation") or ("Undergraduate Student" if age <= 22 else "Graduate Candidate")
    location = "Dhaka, Bangladesh" if index % 2 == 0 else "Chittagong, Bangladesh"

    # Grounded citations
    matched_citations = []
    for c in evidence_claims[:3]:
        matched_citations.append({
            "claim_id": getattr(c, "id", ""),
            "claim_text": getattr(c, "claim_text", ""),
            "category": getattr(c, "category", "general"),
            "confidence": getattr(c, "confidence", 0.85),
        })

    bio = (
        f"{name} is a {age}-year-old {occupation.lower()} based in {location.split(',')[0]}. "
        f"Belongs to the '{seg_name}' market segment with an estimated monthly budget of {currency} {median_budget}. "
        f"Balances academic deadlines with mobile-first study habits."
    )

    quote = (
        f"I need an intelligent tool that keeps my exam milestones on track without costing more than ৳{median_budget}/month."
        if median_budget <= 500
        else "I am willing to pay for advanced analytics and revision schedules if it measurably boosts my score."
    )

    goals = [
        "Maintain structured weekly exam study routines",
        "Minimize distraction across multiple learning resources",
        "Track milestone progress towards semester exams",
    ]

    needs = seg_char.get("needs") or [
        f"Affordable pricing aligned with {currency} {median_budget}/mo budget",
        "Frictionless mobile access with offline capability",
    ]

    pain_points = [
        "Fragmented study notes scattered across chat apps and notebooks",
        "Difficulty estimating remaining revision time before exam deadlines",
        "Frustration with expensive international subscriptions requiring credit cards",
    ]

    behaviors = [
        f"Studies approximately {behav.get('study_hours_per_day', 4.5)} hours per day",
        "Prefers mobile wallet (bKash/Nagad) micro-billing over recurring auto-debit",
        "Collaborates on coursework through peer study groups",
    ]

    preferences = [
        "Dark mode interface with minimal visual clutter",
        "Instant timetable synchronization with exam dates",
    ]

    motivations = [
        "Achieving competitive GPA for university admission or scholarships",
        "Reducing daily scheduling stress and procrastination",
    ]

    objections = [
        "Skeptical of tools requiring upfront long-term annual commitments",
        "Won't use apps that require high-speed continuous internet connectivity",
    ]

    commercial_profile = {
        "monthly_budget_bdt": median_budget,
        "budget_range": budget_range,
        "price_sensitivity": "High" if median_budget <= 400 else "Moderate",
        "payment_preference": "bKash / Nagad Mobile Wallet",
        "willingness_to_pay": f"{currency} {econ.get('min', 250)}–{econ.get('max', 600)} / month",
    }

    technology_profile = {
        "primary_devices": ["Android Smartphone", "Laptop"] if index % 2 == 0 else ["Android Smartphone"],
        "platforms": ["WhatsApp", "Facebook Messenger", "Google Drive"],
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
        archetype=f"{seg_name} Archetype",
        demographics={"age": age, "occupation": occupation, "location": location, "education": "Bachelor's Student", "income_or_budget": f"{currency} {median_budget}/mo"},
        bio=bio,
        quote=quote,
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
    """Generate grounded synthetic customer personas across study segments."""
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
            "2. Each persona must have: name, age, occupation, location, bio (2-3 sentences), quote (1 sentence), "
            "goals (array), needs (array), pain_points (array), behaviors (array), preferences (array), "
            "motivations (array), objections (array), monthly_budget_bdt (number), price_sensitivity, "
            "primary_devices (array), platforms (array), tech_familiarity.\n"
            "3. Ages and budgets must strictly fall within the segment's specified bounds.\n"
            "4. Do NOT invent fictional fairy tales. Make them realistic simulation agents for market research."
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
                name = p_raw.get("name") or _BANGLADESHI_NAMES[global_idx % len(_BANGLADESHI_NAMES)][0]
                age = int(p_raw.get("age", 21))
                occupation = p_raw.get("occupation", "Student")
                location = p_raw.get("location", "Dhaka, Bangladesh")
                budget_num = int(p_raw.get("monthly_budget_bdt", 400))

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
                        "goals": p_raw.get("goals", ["Stay organized"]),
                        "needs": p_raw.get("needs", ["Affordable pricing"]),
                        "pain_points": p_raw.get("pain_points", ["Expensive apps"]),
                        "behaviors": p_raw.get("behaviors", ["Mobile daily user"]),
                        "commercial_profile": {"monthly_budget_bdt": budget_num},
                        "evidence_citations": matched_citations,
                    },
                    seg_char,
                    claims,
                )

                all_generated.append(
                    GeneratedPersonaDraft(
                        name=name,
                        archetype=f"{seg_name} Archetype",
                        demographics={
                            "age": age,
                            "occupation": occupation,
                            "location": location,
                            "education": p_raw.get("education", "Undergraduate"),
                            "income_or_budget": f"৳{budget_num}/mo",
                        },
                        bio=p_raw.get("bio") or f"{name} is a {age}-year-old {occupation} in {location}.",
                        quote=p_raw.get("quote") or "I need an affordable, focused tool.",
                        goals=p_raw.get("goals") or ["Maintain study milestones"],
                        needs=p_raw.get("needs") or ["Affordable pricing"],
                        pain_points=p_raw.get("pain_points") or ["High subscription costs"],
                        behaviors=p_raw.get("behaviors") or ["Uses mobile daily"],
                        preferences=p_raw.get("preferences") or ["Clean distraction-free UI"],
                        motivations=p_raw.get("motivations") or ["Higher exam performance"],
                        objections=p_raw.get("objections") or ["Hesitant about recurring auto-debit"],
                        commercial_profile={
                            "monthly_budget_bdt": budget_num,
                            "price_sensitivity": p_raw.get("price_sensitivity", "High"),
                            "payment_preference": p_raw.get("payment_preference", "bKash Mobile Wallet"),
                            "willingness_to_pay": f"৳{budget_num}/mo",
                        },
                        technology_profile={
                            "primary_devices": p_raw.get("primary_devices", ["Android Smartphone"]),
                            "platforms": p_raw.get("platforms", ["WhatsApp", "Messenger"]),
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
