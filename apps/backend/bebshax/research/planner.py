"""Structured Research Planning Engine for BebshaX.

Analyzes the user's business idea and produces a comprehensive, structured research plan:
- Target Market definition
- Problem Areas & user frictions
- Behavioral research questions
- Economic & Willingness-to-Pay questions
- Competition & Alternative solution questions
- Market size & Macro demographic questions
- High-signal Dataset Requirements (categories, target variables, geographic & population scopes)

Supports LLM-assisted generation via LLMService (TaskType.STRUCTURED_OUTPUT)
with deterministic domain fallback templates.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional
from pydantic import BaseModel, Field

from bebshax.llm.json_utils import parse_llm_json
from bebshax.llm.prompt_safety import UNTRUSTED_RULE, untrusted_block
from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType

logger = logging.getLogger(__name__)


class DatasetRequirementSpec(BaseModel):
    category: str = Field(..., description="High-level dataset domain (e.g., student_spending, food_consumption, sme_operations)")
    description: str = Field(..., description="Why this dataset category is critical to validating the business idea")
    target_variables: list[str] = Field(default_factory=list, description="Specific variables/columns needed for segmentation and profiling")
    geographic_scope: str = Field(default="Bangladesh", description="Preferred geographic region")
    population_scope: str = Field(default="Target Consumers", description="Specific population subset")


class ResearchPlanResult(BaseModel):
    business_idea: str
    target_market: list[str]
    problem_areas: list[str]
    behavioral_questions: list[str]
    economic_questions: list[str]
    competition_questions: list[str]
    market_questions: list[str]
    dataset_requirements: list[DatasetRequirementSpec]
    summary: str
    # Honesty marker: the deterministic keyword template is a starting point,
    # not analysis of THIS idea. Consumers must never present it as LLM output.
    source: str = "deterministic_template"  # "llm" | "deterministic_template"
    fallback_reason: Optional[str] = None


def get_deterministic_research_plan(
    idea: str,
    target_audience: Optional[str] = None,
    pricing_hypothesis: Optional[str] = None,
) -> ResearchPlanResult:
    """Generate a rich deterministic research plan across key business verticals."""
    lower_idea = idea.lower()

    # 1. B2B SaaS / Accounting / Restaurant & SME Software
    if re.search(r"accounting|pos|sme|b2b|inventory|invoice|saas|billing|ledger", lower_idea):
        return ResearchPlanResult(
            business_idea=idea,
            target_market=[
                "Small to Medium Restaurant & Cafe Operators",
                "Retail Shop & Cloud Kitchen Managers",
                "Sole Proprietors & Small Business Owners",
            ],
            problem_areas=[
                "Manual bookkeeping leading to revenue leakage and unrecorded inventory spoilage",
                "Complex enterprise ERP systems that are unaffordable and overwhelming for local staff",
                "Fragmented reconciliation across cash sales, card POS, and mobile payments (bKash/Nagad)",
                "Lack of real-time visibility into daily unit economics and profit margins",
            ],
            behavioral_questions=[
                "What manual tools (notebooks, Excel spreadsheets, registers) are currently used for daily accounts?",
                "How much time do business owners spend daily reconciling cash and digital transactions?",
                "Who makes the software purchasing decisions and operates the daily transaction terminal?",
            ],
            economic_questions=[
                "What is the average monthly operating budget for business software tools (৳500–৳2,500/mo)?",
                "What ROI or cost-reduction threshold is required before an owner commits to recurring SaaS fees?",
                "Do small businesses prefer flat monthly fees or transaction-based micro-commissions?",
            ],
            competition_questions=[
                "What legacy on-premise POS or local accounting software solutions are currently installed?",
                "Why do small restaurants resist transitioning from paper ledgers to digital billing?",
            ],
            market_questions=[
                "What is the total number of registered and informal food service & retail SMEs in Bangladesh?",
                "What is the annual growth rate of digital payment adoption in urban retail establishments?",
            ],
            dataset_requirements=[
                DatasetRequirementSpec(
                    category="sme_operations",
                    description="Financial operations, revenue bands, and expense breakdowns for small businesses",
                    target_variables=["monthly_revenue_bdt", "software_budget_bdt", "employee_count", "daily_transaction_volume"],
                    geographic_scope="Bangladesh",
                    population_scope="Small & Medium Enterprises",
                ),
                DatasetRequirementSpec(
                    category="digital_adoption",
                    description="Digital tool adoption, POS penetration, and mobile banking reconciliation data",
                    target_variables=["pos_adoption_status", "digital_payment_ratio", "inventory_loss_rate"],
                    geographic_scope="South Asia / Bangladesh",
                    population_scope="Retail & Food Service Operators",
                ),
            ],
            summary="Autonomous research plan investigating SME accounting automation, operational friction, and commercial pricing willingness.",
        )

    # 2. Food & Meal Planning / Delivery
    if re.search(r"meal|food|diet|nutrition|restaurant|cooking|recipe|delivery|cater", lower_idea):
        is_student = bool(re.search(r"student|university|campus|college", lower_idea))
        target = (
            ["University Students in Bangladesh (18–24)", "Campus Dormitory & Hall Residents", "Budget-Conscious Young Adults"]
            if is_student
            else ["Urban Working Professionals & Families", "Health-Conscious Meal Planners", "Home Cooks & Food Enthusiasts"]
        )
        return ResearchPlanResult(
            business_idea=idea,
            target_market=target,
            problem_areas=[
                "Daily decision fatigue in meal selection and grocery planning",
                "High expenditure and health risks associated with frequent unmonitored fast food delivery",
                "Limited kitchen facilities or cooking time balancing daily commitments",
                "Difficulty maintaining balanced nutrition within a tight monthly food allowance",
            ],
            behavioral_questions=[
                "How frequently do target consumers cook at home vs order from delivery apps or local cafeterias?",
                "How many minutes per day are consumers willing to dedicate to meal preparation?",
                "What digital tools or social channels are currently used to find recipes and grocery prices?",
            ],
            economic_questions=[
                f"What is the average monthly food budget per person in BDT (baseline: ৳{3500 if is_student else 8000}–৳{6000 if is_student else 15000})?",
                "What is the maximum acceptable monthly subscription ceiling for an automated meal planning app?",
                "What payment channels (e.g. bKash, Nagad, Card) offer the lowest barrier to adoption?",
            ],
            competition_questions=[
                "How do existing food delivery platforms (Foodpanda, Pathao Food) dominate meal occasions?",
                "Why have Western meal-planning apps (Mealime, MyFitnessPal) failed to capture the local market?",
                "What friction exists when ordering raw groceries via local quick-commerce (Chaldal, Shwapno)?",
            ],
            market_questions=[
                "What is the total addressable urban student/young adult population in major cities (Dhaka, Chittagong)?",
                "What percentage of disposable income is allocated to food and groceries across target socio-economic tiers?",
            ],
            dataset_requirements=[
                DatasetRequirementSpec(
                    category="food_spending",
                    description="Household and individual food expenditure distributions in Bangladesh",
                    target_variables=["monthly_budget_bdt", "food_spend_percentage", "meal_count_daily", "dining_out_frequency"],
                    geographic_scope="Bangladesh",
                    population_scope="University Students & Young Adults" if is_student else "Urban Consumers",
                ),
                DatasetRequirementSpec(
                    category="food_consumption",
                    description="Daily dietary intake, meal timing, and nutritional composition data",
                    target_variables=["calories_per_day", "cooking_time_minutes", "protein_intake_grams", "preferred_cuisine"],
                    geographic_scope="Bangladesh",
                    population_scope="Urban Households",
                ),
                DatasetRequirementSpec(
                    category="demographics_lifestyle",
                    description="Demographic profile, living arrangement, and smartphone adoption metrics",
                    target_variables=["age", "gender", "living_arrangement", "smartphone_usage_hours"],
                    geographic_scope="Bangladesh",
                    population_scope="Students & Young Professionals",
                ),
            ],
            summary="Autonomous research plan exploring consumer meal planning habits, affordability constraints, and nutritional willingness-to-pay in Bangladesh.",
        )

    # 3. Education / Language Learning / EdTech / Exam Prep
    if re.search(r"education|learn|english|language|tutor|exam|test|student|course|study|bcs", lower_idea):
        return ResearchPlanResult(
            business_idea=idea,
            target_market=[
                "University Students & BCS/Govt Job Candidates",
                "High School & College Examination Candidates",
                "Early Career Professionals seeking English Fluency",
            ],
            problem_areas=[
                "High cost and rigid schedules of traditional coaching centers and private tutors",
                "Lack of individualized diagnostic feedback on syllabus weak points and pronunciation errors",
                "Poor access to high-quality interactive practice materials outside major metropolitan hubs",
                "Low motivation and high dropout rates in self-paced video courses lacking accountability",
            ],
            behavioral_questions=[
                "How many hours per week do students dedicate to exam prep or self-directed learning?",
                "What devices (mobile Android vs laptop) are primarily used for interactive practice?",
                "Do learners prefer gamified micro-lessons (10–15 min) or intensive mock exam sessions?",
            ],
            economic_questions=[
                "What is the current monthly expenditure on coaching centers, books, and private tutoring (৳500–৳3,000/mo)?",
                "What is the willingness to pay for an AI-powered instant diagnostic tool with unlimited mock questions?",
                "How do students react to tiered pricing (free daily questions vs premium unlimited access)?",
            ],
            competition_questions=[
                "What offline coaching institutes (Udvash, UCC, Saifur's) dominate candidate trust?",
                "How do local edtech platforms (10 Minute School, Shikho) structure their pricing and course delivery?",
            ],
            market_questions=[
                "How many candidates sit annually for HSC, University Admission, and BCS competitive exams in Bangladesh?",
                "What is the broadband and 4G data access penetration among tertiary students outside Dhaka?",
            ],
            dataset_requirements=[
                DatasetRequirementSpec(
                    category="student_education",
                    description="Academic study hours, exam preparation spending, and learning outcomes",
                    target_variables=["daily_study_hours", "education_spend_monthly_bdt", "exam_target_type", "device_access"],
                    geographic_scope="Bangladesh",
                    population_scope="University & Exam Candidates",
                ),
                DatasetRequirementSpec(
                    category="edtech_adoption",
                    description="Digital learning engagement, mobile app retention, and subscription conversion metrics",
                    target_variables=["daily_active_minutes", "willingness_to_pay_bdt", "retention_rate_30d"],
                    geographic_scope="Bangladesh",
                    population_scope="Tertiary Students",
                ),
            ],
            summary="Autonomous research plan exploring edtech adoption, exam preparation behavior, and willingness-to-pay for AI tutoring.",
        )

    # 4. E-Commerce & Marketplace / Fashion / Retail
    if re.search(r"e-commerce|ecommerce|shop|clothing|fashion|marketplace|sustainable|apparel|buy|sell", lower_idea):
        return ResearchPlanResult(
            business_idea=idea,
            target_market=[
                "Young Urban Consumers (20–35)",
                "Eco-Conscious & Trend-Focused Shoppers",
                "Active Social Commerce (F-commerce) Buyers",
            ],
            problem_areas=[
                "Inconsistent product quality and sizing discrepancies in online apparel shopping",
                "High return friction and lack of trust in payment before physical inspection",
                "Difficulty discovering authentic sustainable/ethical clothing at accessible local price points",
                "Slow delivery times and high cash-on-delivery cancellation rates",
            ],
            behavioral_questions=[
                "How often do consumers purchase clothing online per quarter?",
                "What factors (price, design, eco-certification, influencer endorsement) drive checkout conversion?",
                "What is the preferred discovery channel (Instagram, Facebook live, dedicated website)?",
            ],
            economic_questions=[
                "What is the average order value (AOV) for apparel purchases in BDT (৳800–৳2,500)?",
                "What price premium are consumers willing to pay for verifiably sustainable garments?",
                "How does offering free delivery or bKash cashback influence purchase decisions?",
            ],
            competition_questions=[
                "How do major marketplaces (Daraz, Aarong, local F-commerce boutiques) compete on fashion?",
                "Why do boutique apparel brands struggle with repeat retention and customer lifetime value?",
            ],
            market_questions=[
                "What is the total market size of the online domestic fashion & lifestyle retail sector in Bangladesh?",
                "What percentage of urban apparel shoppers prioritize sustainable/ethical manufacturing?",
            ],
            dataset_requirements=[
                DatasetRequirementSpec(
                    category="consumer_ecommerce",
                    description="Online shopping frequency, category spending, and payment method preferences",
                    target_variables=["monthly_online_spend_bdt", "order_frequency_monthly", "preferred_payment_mode", "return_rate"],
                    geographic_scope="Bangladesh",
                    population_scope="Urban E-Commerce Shoppers",
                ),
                DatasetRequirementSpec(
                    category="fashion_spending",
                    description="Apparel spending patterns, sustainability willingness, and brand preferences",
                    target_variables=["apparel_budget_bdt", "sustainable_price_tolerance", "brand_loyalty_score"],
                    geographic_scope="Bangladesh",
                    population_scope="Young Adults & Professionals",
                ),
            ],
            summary="Autonomous research plan analyzing consumer fashion shopping patterns, willingness to pay, and marketplace trust barriers.",
        )

    # 5. Generic / Multi-Vertical Fallback
    return ResearchPlanResult(
        business_idea=idea,
        target_market=[
            target_audience or "Core Target Consumers / Businesses in Bangladesh",
            "Early Adopter Segment with immediate need",
            "Price-Sensitive Mainstream Segment",
        ],
        problem_areas=[
            "High friction in current manual or fragmented alternative solutions",
            "Lack of accessible, locally tailored digital tools with local payment support",
            "Unclear value-to-cost ratio in existing high-end competitor offerings",
            "Information asymmetry and distrust in unverified claims",
        ],
        behavioral_questions=[
            "What daily workflow or routine does the target user follow currently to address this need?",
            "What triggers the user to actively search for and adopt a new solution?",
            "Which communication platforms and devices are essential for user onboarding?",
        ],
        economic_questions=[
            pricing_hypothesis or "What is the acceptable monthly budget range for target users in BDT?",
            "What is the price sensitivity floor where users perceive the offering as high value?",
            "What payment options (bKash, Nagad, Cards, Cash) convert best?",
        ],
        competition_questions=[
            "What are the top 3 direct and indirect alternatives used today?",
            "What are the primary reasons users churn or refuse to switch from existing alternatives?",
        ],
        market_questions=[
            "What is the total addressable audience size in Bangladesh's major urban centers?",
            "What macroeconomic and demographic trends are driving demand growth in this domain?",
        ],
        dataset_requirements=[
            DatasetRequirementSpec(
                category="demographic_expenditure",
                description="Household income, spending distributions, and demographic profiles",
                target_variables=["monthly_income_bdt", "discretionary_spend_bdt", "age", "occupation", "urban_tier"],
                geographic_scope="Bangladesh",
                population_scope="Target Market Consumers",
            ),
            DatasetRequirementSpec(
                category="digital_adoption",
                description="Smartphone ownership, mobile financial services usage, and internet engagement",
                target_variables=["internet_usage_hours", "mfs_wallet_adoption", "app_spending_willingness"],
                geographic_scope="Bangladesh",
                population_scope="Active Internet Users",
            ),
        ],
        summary=f"Autonomous research plan examining target customer demand, friction points, and commercial viability for: {idea}",
    )


async def generate_structured_research_plan(
    idea: str,
    target_audience: Optional[str] = None,
    pricing_hypothesis: Optional[str] = None,
    llm_service: Optional[LLMService] = None,
) -> ResearchPlanResult:
    """Generate a structured research plan utilizing LLMService when available, with deterministic fallback."""
    if not llm_service:
        plan = get_deterministic_research_plan(idea, target_audience, pricing_hypothesis)
        return plan.model_copy(update={"fallback_reason": "llm_service_unavailable"})

    # Researcher text is DATA: wrapped so it cannot restate the instructions, and
    # JSON-encoded inside the schema template so quotes cannot break out of the
    # "business_idea" string.
    context_lines = [f"BUSINESS IDEA: {idea}"]
    if target_audience:
        context_lines.append(f"TARGET AUDIENCE: {target_audience}")
    if pricing_hypothesis:
        context_lines.append(f"PRICING HYPOTHESIS: {pricing_hypothesis}")
    context_block = untrusted_block("RESEARCH_BRIEF", "\n".join(context_lines), source="study")

    prompt = f"""You are the Chief Research Officer for BebshaX, an empirical customer validation platform.
Analyze the following business idea and generate a comprehensive, structured research plan to discover evidence and public datasets.
{UNTRUSTED_RULE}

{context_block}

Produce a valid JSON object matching this exact schema:
{{
  "business_idea": {json.dumps(idea, ensure_ascii=False)},
  "target_market": ["segment 1", "segment 2", "segment 3"],
  "problem_areas": ["problem 1", "problem 2", "problem 3", "problem 4"],
  "behavioral_questions": ["question 1", "question 2", "question 3"],
  "economic_questions": ["question 1 regarding willingness to pay and budget", "question 2", "question 3"],
  "competition_questions": ["question 1 on alternatives", "question 2"],
  "market_questions": ["question 1 on market size and demographics", "question 2"],
  "dataset_requirements": [
    {{
      "category": "dataset_category_name",
      "description": "Why this dataset is essential",
      "target_variables": ["variable_1", "variable_2", "variable_3"],
      "geographic_scope": "Bangladesh or regional scope",
      "population_scope": "Specific population group"
    }}
  ],
  "summary": "Concise 1-2 sentence overview of the research scope"
}}

Respond ONLY with valid JSON."""

    try:
        req = LLMRequest(
            task=TaskType.STRUCTURED_OUTPUT,
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=0.3,
            max_output_tokens=1500,
        )
        res = await llm_service.complete(req)
        data = parse_llm_json(res.text)
        reqs = [
            DatasetRequirementSpec(
                category=r.get("category", "demographics"),
                description=r.get("description", "Relevant dataset"),
                target_variables=r.get("target_variables", []),
                geographic_scope=r.get("geographic_scope", "Bangladesh"),
                population_scope=r.get("population_scope", "Target population"),
            )
            for r in data.get("dataset_requirements", [])
        ]
        if not reqs:
            raise ValueError("No dataset requirements generated")

        return ResearchPlanResult(
            business_idea=idea,
            target_market=data.get("target_market", []),
            problem_areas=data.get("problem_areas", []),
            behavioral_questions=data.get("behavioral_questions", []),
            economic_questions=data.get("economic_questions", []),
            competition_questions=data.get("competition_questions", []),
            market_questions=data.get("market_questions", []),
            dataset_requirements=reqs,
            summary=data.get("summary", f"Research plan for {idea}"),
            source="llm",
        )
    except Exception as exc:
        logger.warning("LLM research plan generation failed (%s), falling back to deterministic template", exc)
        plan = get_deterministic_research_plan(idea, target_audience, pricing_hypothesis)
        return plan.model_copy(update={"fallback_reason": f"llm_error:{type(exc).__name__}"})
