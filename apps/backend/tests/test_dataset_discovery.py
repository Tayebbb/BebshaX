"""Unit tests for Dataset Discovery Adapters and Evaluator."""

import httpx
import pytest
from bebshax.datasets.discovery.bbs_adapter import BBSOpenDataAdapter
from bebshax.datasets.discovery.evaluator import DatasetEvaluator
from bebshax.datasets.discovery.kaggle_adapter import KaggleOpenDataAdapter
from bebshax.datasets.discovery.world_bank_adapter import WorldBankOpenDataAdapter
from bebshax.datasets.parser import parse_dataset_bytes
from bebshax.research.planner import DatasetRequirementSpec


def _offline_handler(request: httpx.Request) -> httpx.Response:
    """Simulates a venue with no internet — every request fails to connect."""
    raise httpx.ConnectError("network unreachable", request=request)


def _offline_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(_offline_handler))


def _wb_live_handler(request: httpx.Request) -> httpx.Response:
    """Serves a canned World Bank v2 payload: [page-metadata, rows] with one null value."""
    assert request.url.host == "api.worldbank.org"
    code = request.url.path.rsplit("/", 1)[-1]
    payload = [
        {"page": 1, "pages": 1, "per_page": 100, "total": 3},
        [
            {
                "indicator": {"id": code, "value": "Indicator name"},
                "country": {"id": "BD", "value": "Bangladesh"},
                "countryiso3code": "BGD",
                "date": "2024",
                "value": 9.88,
            },
            {"indicator": {"id": code}, "country": {"id": "BD"}, "date": "2023", "value": 9.02},
            {"indicator": {"id": code}, "country": {"id": "BD"}, "date": "2022", "value": None},
        ],
    ]
    return httpx.Response(200, json=payload)


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
    # Honest labeling: the catalog never attributes generated samples to the real publisher.
    assert hies.publisher.startswith("BebshaX Illustrative Catalog")
    assert "Bangladesh Bureau of Statistics" in hies.publisher  # modeled-on attribution kept
    assert hies.is_sample is True
    assert "bebshax.example" in hies.url  # no fabricated real-domain URLs
    assert hies.download_url is None
    assert "monthly_food_spend_bdt" in hies.relevant_variables
    assert hies.raw_data_content is not None
    assert len(hies.raw_data_content) > 100


@pytest.mark.asyncio
async def test_world_bank_adapter_search():
    """Network failure -> the illustrative fallback catalog is served intact (offline demo path)."""
    reqs = [
        DatasetRequirementSpec(
            category="digital_payments",
            description="Mobile money and digital payment adoption",
            target_variables=["has_mfs_account", "monthly_digital_transactions"],
        )
    ]
    async with _offline_client() as client:
        adapter = WorldBankOpenDataAdapter(http_client=client)
        candidates = await adapter.search(["bKash mobile wallet digital payments Bangladesh"], reqs)
    assert len(candidates) >= 1
    findex = candidates[0]
    # Honest labeling: illustrative catalog with modeled-on attribution.
    assert findex.publisher.startswith("BebshaX Illustrative Catalog")
    assert "World Bank" in findex.publisher
    assert findex.is_sample is True
    assert "bebshax.example" in findex.url
    assert findex.format == "csv"


@pytest.mark.asyncio
async def test_world_bank_live_success_returns_real_data():
    """Live API reachable -> candidates carry real api.worldbank.org URLs and is_sample=False."""
    reqs = [
        DatasetRequirementSpec(
            category="digital_payments",
            description="Mobile money and digital payment adoption",
            target_variables=["has_mfs_account", "monthly_digital_transactions"],
        )
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(_wb_live_handler)) as client:
        adapter = WorldBankOpenDataAdapter(http_client=client)
        candidates = await adapter.search(["bKash mobile wallet digital payments Bangladesh"], reqs)

    assert 2 <= len(candidates) <= 4
    for cand in candidates:
        assert cand.is_sample is False
        assert cand.source == "World Bank Open Data (live)"
        assert cand.publisher == "World Bank Open Data (live)"
        assert cand.url.startswith("https://api.worldbank.org/v2/country/BGD/indicator/")
        assert cand.raw_data_content is not None
        # Import-compat: the engine parses raw_data_content with the same parser.
        columns, rows = parse_dataset_bytes(cand.raw_data_content.encode("utf-8"), file_type="csv")
        assert columns == ["country", "indicator_code", "indicator_name", "year", "value"]
        # The null-valued 2022 observation is skipped.
        assert len(rows) == cand.sample_rows == 2
        assert {row["year"] for row in rows} == {2023, 2024}


@pytest.mark.asyncio
async def test_world_bank_malformed_payload_falls_back_to_illustrative():
    """A 200 response with an unexpected shape must not crash — illustrative fallback instead."""

    def malformed_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    reqs = [
        DatasetRequirementSpec(
            category="digital_payments",
            description="Mobile money and digital payment adoption",
            target_variables=["has_mfs_account"],
        )
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(malformed_handler)) as client:
        adapter = WorldBankOpenDataAdapter(http_client=client)
        candidates = await adapter.search(["bKash digital payments Bangladesh"], reqs)

    assert len(candidates) >= 1
    assert all(c.is_sample for c in candidates)
    assert all(c.publisher.startswith("BebshaX Illustrative Catalog") for c in candidates)
    assert all("bebshax.example" in c.url for c in candidates)


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
    # Honest labeling: every catalog entry is flagged as an illustrative sample.
    assert all(c.is_sample for c in candidates)
    assert all(c.publisher.startswith("BebshaX Illustrative Catalog") for c in candidates)


@pytest.mark.asyncio
async def test_dataset_evaluator_scoring_and_diversity():
    evaluator = DatasetEvaluator(max_auto_select=3)
    bbs = BBSOpenDataAdapter()
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
    async with _offline_client() as client:
        wb = WorldBankOpenDataAdapter(http_client=client)
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
