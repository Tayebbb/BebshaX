"""Unit tests for Dataset Discovery Adapters and Evaluator."""

import pytest
from bebshax.datasets.discovery.bbs_adapter import BBSOpenDataAdapter
from bebshax.datasets.discovery.evaluator import DatasetEvaluator
from bebshax.datasets.discovery.kaggle_adapter import KaggleOpenDataAdapter
from bebshax.datasets.discovery.world_bank_adapter import WorldBankOpenDataAdapter
from bebshax.research.planner import DatasetRequirementSpec


@pytest.mark.asyncio
async def test_bbs_adapter_search():
    adapter = BBSOpenDataAdapter()
    reqs = [
        DatasetRequirementSpec(
            category="food_spending",
            description="Household food expenditure in Bangladesh",
            target_variables=["monthly_food_spend_bdt", "monthly_income_bdt"],
        )
    ]
    candidates = await adapter.search(["student meal food expenditure in Bangladesh"], reqs)
    assert len(candidates) >= 1

    hies = next((c for c in candidates if "hies" in c.external_id), None)
    assert hies is not None
    assert hies.publisher.startswith("Bangladesh Bureau of Statistics")
    assert "monthly_food_spend_bdt" in hies.relevant_variables
    assert hies.raw_data_content is not None
    assert len(hies.raw_data_content) > 100


@pytest.mark.asyncio
async def test_world_bank_adapter_search():
    adapter = WorldBankOpenDataAdapter()
    reqs = [
        DatasetRequirementSpec(
            category="digital_payments",
            description="Mobile money and digital payment adoption",
            target_variables=["has_mfs_account", "monthly_digital_transactions"],
        )
    ]
    candidates = await adapter.search(["bKash mobile wallet digital payments Bangladesh"], reqs)
    assert len(candidates) >= 1
    findex = candidates[0]
    assert "World Bank" in findex.publisher
    assert findex.format == "csv"


@pytest.mark.asyncio
async def test_kaggle_adapter_search():
    adapter = KaggleOpenDataAdapter()
    reqs = [
        DatasetRequirementSpec(
            category="food_behavior",
            description="Student food delivery orders and habits",
            target_variables=["meals_cooked_weekly", "delivery_orders_weekly"],
        )
    ]
    candidates = await adapter.search(["student food delivery app usage"], reqs)
    assert len(candidates) >= 1
    assert any("student" in c.external_id for c in candidates)


@pytest.mark.asyncio
async def test_dataset_evaluator_scoring_and_diversity():
    evaluator = DatasetEvaluator(max_auto_select=3)
    bbs = BBSOpenDataAdapter()
    wb = WorldBankOpenDataAdapter()
    kaggle = KaggleOpenDataAdapter()

    idea = "AI meal planner app for university students in Bangladesh"
    reqs = [
        DatasetRequirementSpec(
            category="food_spending",
            description="Student and household food expenditure",
            target_variables=["monthly_food_spend_bdt", "monthly_budget_bdt"],
            geographic_scope="Bangladesh",
            population_scope="University Students",
        )
    ]

    all_cands = []
    all_cands.extend(await bbs.search([idea], reqs))
    all_cands.extend(await wb.search([idea], reqs))
    all_cands.extend(await kaggle.search([idea], reqs))

    results = evaluator.evaluate_candidates(all_cands, idea, reqs)
    assert len(results) >= 2

    # Verify scores
    for r in results:
        assert 0.50 <= r.relevance_score <= 0.98
        assert 0.50 <= r.quality_score <= 0.98
        assert len(r.selection_reason) > 10

    # Verify selection count
    selected = [r for r in results if r.is_selected]
    assert 1 <= len(selected) <= 3

    # Verify diversity
    selected_categories = [r.candidate.category for r in selected]
    assert len(selected_categories) == len(set(selected_categories))
