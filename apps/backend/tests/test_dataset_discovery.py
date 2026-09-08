"""Unit tests for Dataset Discovery adapters, downloader, evaluator and engine.

Every source is live and keyless; tests replace the network with
``httpx.MockTransport``. No test may pass on an invented catalogue.
"""

import json

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.datasets.discovery.base_adapter import DatasetCandidateData
from bebshax.datasets.discovery.ckan_adapter import CKANDatasetAdapter
from bebshax.datasets.discovery.downloader import DatasetDownloadFailed, fetch_resource_bytes
from bebshax.datasets.discovery.engine import DatasetDiscoveryEngine, default_adapters
from bebshax.datasets.discovery.evaluator import DatasetEvaluator
from bebshax.datasets.discovery.world_bank_adapter import WorldBankOpenDataAdapter, select_indicators
from bebshax.datasets.parser import parse_dataset_bytes
from bebshax.db.models import Base, DatasetCandidates, DatasetSources
from bebshax.research.planner import DatasetRequirementSpec


def _offline_handler(request: httpx.Request) -> httpx.Response:
    """Simulates a venue with no internet — every request fails to connect."""
    raise httpx.ConnectError("network unreachable", request=request)


def _offline_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(_offline_handler))


def _wb_payload(code: str, country: str) -> list:
    names = {"PRT": "Portugal", "BGD": "Bangladesh"}
    return [
        {"page": 1, "pages": 1, "per_page": 100, "total": 3},
        [
            {"indicator": {"id": code, "value": "Indicator name"}, "country": {"id": country[:2], "value": names.get(country, country)},
             "countryiso3code": country, "date": "2024", "value": 9.88},
            {"indicator": {"id": code}, "country": {"id": country[:2], "value": names.get(country, country)}, "date": "2023", "value": 9.02},
            {"indicator": {"id": code}, "country": {"id": country[:2]}, "date": "2022", "value": None},
        ],
    ]


def _wb_live_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.host == "api.worldbank.org"
    parts = request.url.path.split("/")
    country = parts[parts.index("country") + 1]
    code = parts[-1]
    return httpx.Response(200, json=_wb_payload(code, country))


_REQS = [
    DatasetRequirementSpec(
        category="cafe_operations",
        description="Independent café turnover, card payment share and staffing in Lisbon",
        target_variables=["monthly_turnover", "card_payment_share"],
        geographic_scope="Lisbon, Portugal",
        population_scope="independent cafés",
    )
]
_QUERIES = ["café point of sale payments Lisbon", "small restaurant card payment adoption Portugal"]


# ── World Bank ────────────────────────────────────────────────────────────────


def test_indicator_selection_follows_the_study_text():
    codes, topical = select_indicators("mobile payments app for café owners internet banking")
    assert topical and "IT.NET.USER.ZS" in codes and "FB.ATM.TOTL.P5" in codes
    macro, topical = select_indicators("zzz qqq")  # nothing matches -> labelled macro context only
    assert not topical and macro == ["NY.GDP.PCAP.CD", "SP.POP.TOTL"]


@pytest.mark.asyncio
async def test_world_bank_uses_the_plans_countries_and_never_assumes_one():
    async with httpx.AsyncClient(transport=httpx.MockTransport(_wb_live_handler)) as client:
        adapter = WorldBankOpenDataAdapter(http_client=client)
        none = await adapter.search(_QUERIES, _REQS, countries=[])
        assert none == []  # no country in the plan -> no dataset, no default geography

        candidates = await adapter.search(_QUERIES, _REQS, countries=["PRT", "not-a-code"])
    assert candidates and all(c.geographic_coverage == "Portugal" for c in candidates)
    assert all(c.is_sample is False and c.download_url.startswith("https://api.worldbank.org/v2/country/PRT/") for c in candidates)
    assert all(c.sample_rows == 2 for c in candidates)  # the null observation is dropped
    columns, rows = parse_dataset_bytes(candidates[0].raw_data_content.encode(), file_type="csv")
    assert columns == ["country", "indicator_code", "indicator_name", "year", "value"]
    assert [r["year"] for r in rows] == [2023, 2024] and rows[0]["country"] == "Portugal"


@pytest.mark.asyncio
async def test_world_bank_offline_returns_nothing():
    async with _offline_client() as client:
        assert await WorldBankOpenDataAdapter(http_client=client).search(_QUERIES, _REQS, countries=["BGD"]) == []


@pytest.mark.asyncio
async def test_world_bank_malformed_payload_returns_nothing():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"unexpected": True}))) as client:
        assert await WorldBankOpenDataAdapter(http_client=client).search(_QUERIES, _REQS, countries=["BGD"]) == []


# ── CKAN portals ─────────────────────────────────────────────────────────────


def _ckan_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/api/3/action/package_search"
    q = request.url.params["q"]
    if "payments" not in q and "payment" not in q:
        return httpx.Response(200, json={"success": True, "result": {"count": 0, "results": []}})
    pkg = {
        "name": "cafe-card-payments-lisbon-2024",
        "title": "Card payments at independent cafés — Lisbon 2024",
        "notes": "Monthly turnover and card payment share for 340 independent cafés in Lisbon, Portugal.",
        "organization": {"title": "Lisbon Open Data Office"},
        "license_title": "Creative Commons Attribution",
        "license_url": "http://www.opendefinition.org/licenses/cc-by",
        "metadata_modified": "2025-11-02T10:00:00.000000",
        "tags": [{"name": "payments"}, {"name": "cafe"}, {"name": "turnover"}],
        "groups": [{"name": "prt", "title": "Portugal"}],
        "resources": [
            {"url": "https://files.example.org/cafes.pdf", "format": "PDF"},
            {"url": "https://files.example.org/cafes.csv", "format": "CSV", "size": 20480},
        ],
    }
    return httpx.Response(200, json={"success": True, "result": {"count": 1, "results": [pkg]}})


@pytest.mark.asyncio
async def test_ckan_adapter_maps_real_packages_and_prefers_csv_resources():
    async with httpx.AsyncClient(transport=httpx.MockTransport(_ckan_handler)) as client:
        adapter = CKANDatasetAdapter.hdx(http_client=client)
        candidates = await adapter.search(_QUERIES, _REQS)
    assert len(candidates) == 1  # deduplicated across the two matching queries
    c = candidates[0]
    assert c.source == "Humanitarian Data Exchange (HDX)"
    assert c.url == "https://data.humdata.org/dataset/cafe-card-payments-lisbon-2024"
    assert c.download_url == "https://files.example.org/cafes.csv" and c.format == "csv"
    assert c.size_bytes == 20480 and c.license == "Creative Commons Attribution"
    assert c.publisher == "Lisbon Open Data Office" and c.geographic_coverage == "Portugal"
    assert c.tags == ["payments", "cafe", "turnover"] and c.modified_at.startswith("2025-11-02")
    assert c.sample_rows is None and c.is_sample is False  # unknown stays unknown


@pytest.mark.asyncio
async def test_ckan_offline_or_error_returns_nothing():
    async with _offline_client() as client:
        assert await CKANDatasetAdapter.datagov(http_client=client).search(_QUERIES, _REQS) == []
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as client:
        assert await CKANDatasetAdapter.datagov(http_client=client).search(_QUERIES, _REQS) == []


def test_default_adapters_are_all_live_sources():
    names = [a.source_name for a in default_adapters()]
    assert names == ["World Bank Open Data", "Humanitarian Data Exchange (HDX)", "data.gov"]
    assert not any("Illustrative" in n for n in names)


# ── Downloader ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_downloader_enforces_scheme_status_and_size():
    with pytest.raises(DatasetDownloadFailed):
        await fetch_resource_bytes("ftp://files.example.org/x.csv")

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as client:
        with pytest.raises(DatasetDownloadFailed) as info:
            await fetch_resource_bytes("https://files.example.org/x.csv", http_client=client)
        assert "HTTP 404" in info.value.detail and info.value.status_code == 502

    big = httpx.MockTransport(lambda r: httpx.Response(200, content=b"a,b\n" * 100, headers={"content-length": "999999999"}))
    async with httpx.AsyncClient(transport=big) as client:
        with pytest.raises(DatasetDownloadFailed) as info:
            await fetch_resource_bytes("https://files.example.org/x.csv", http_client=client)
        assert "at most" in info.value.detail

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"a,b\n1,2\n" * 50))) as client:
        with pytest.raises(DatasetDownloadFailed):
            await fetch_resource_bytes("https://files.example.org/x.csv", http_client=client, max_bytes=100)
        body, meta = await fetch_resource_bytes("https://files.example.org/x.csv", http_client=client)
    assert body.startswith(b"a,b\n1,2") and meta["size_bytes"] == len(body)


# ── Evaluator ────────────────────────────────────────────────────────────────


def _cand(**overrides) -> DatasetCandidateData:
    base = dict(
        source="Humanitarian Data Exchange (HDX)",
        external_id="x",
        name="Card payments at independent cafés — Lisbon 2024",
        description="Monthly turnover and card payment share for independent cafés in Lisbon, Portugal.",
        url="https://data.humdata.org/dataset/x",
        download_url="https://files.example.org/cafes.csv",
        publisher="Lisbon Open Data Office",
        license="Creative Commons Attribution",
        format="csv",
        size_bytes=20480,
        modified_at="2025-11-02T10:00:00",
        tags=["payments", "cafe", "turnover"],
        relevant_variables=["payments", "cafe", "turnover", "monthly_turnover"],
        geographic_coverage="Portugal",
        category="economy",
    )
    base.update(overrides)
    return DatasetCandidateData(**base)


def test_evaluator_scores_are_computed_from_the_study_not_a_geography_table():
    evaluator = DatasetEvaluator(max_auto_select=2)
    idea = "Point-of-sale and card payment software for independent cafés in Lisbon"
    related = _cand()
    unrelated = _cand(external_id="y", name="Antarctic krill catch statistics 1990-2010", description="Annual krill tonnage by vessel.",
                      tags=["fisheries"], relevant_variables=["tonnage"], geographic_coverage="Antarctica", category="environment")
    listing_only = _cand(external_id="z", download_url=None, license="", size_bytes=None, modified_at=None)

    results = evaluator.evaluate_candidates([unrelated, related, listing_only], idea, _REQS, _QUERIES)
    by_id = {r.candidate.external_id: r for r in results}

    assert by_id["x"].relevance_score > 0.5 > by_id["y"].relevance_score
    assert by_id["y"].relevance_score < 0.1
    assert "Geography matches the plan" in " ".join(by_id["x"].evaluation_details["relevance_reasons"])
    assert "No vocabulary shared" in " ".join(by_id["y"].evaluation_details["relevance_reasons"])
    assert by_id["x"].quality_score > by_id["z"].quality_score
    assert "Listing only" in " ".join(by_id["z"].evaluation_details["quality_reasons"])
    assert by_id["x"].is_selected and not by_id["y"].is_selected
    dumped = json.dumps([r.model_dump() for r in results])
    for banned in ("Bangladesh", "Illustrative", "Modeled on"):
        assert banned not in dumped


# ── Engine ───────────────────────────────────────────────────────────────────


class _OneCandidateAdapter:
    def __init__(self, candidate: DatasetCandidateData) -> None:
        self._c = candidate
        self.received: dict = {}

    @property
    def source_name(self) -> str:
        return "test-source"

    async def search(self, queries, requirements, *, countries=None):
        self.received = {"queries": queries, "countries": countries}
        return [self._c]


@pytest.mark.asyncio
async def test_engine_imports_selected_candidates_by_downloading_the_real_resource(tmp_path, monkeypatch):
    monkeypatch.setenv("BEBSHAX_UPLOAD_DIR", str(tmp_path))
    from bebshax.config import get_settings

    get_settings.cache_clear()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    csv_body = "cafe_id,monthly_turnover,card_payment_share,district\n" + "\n".join(
        f"c{i},{4000 + i * 100},{0.3 + i * 0.01:.2f},{'Baixa' if i % 2 else 'Alfama'}" for i in range(30)
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://files.example.org/cafes.csv"
        return httpx.Response(200, content=csv_body.encode(), headers={"content-type": "text/csv"})

    good = _cand()
    dead = _cand(external_id="dead", name="Card payments cafés Lisbon (broken link)", download_url="https://files.example.org/missing.csv", category="other")

    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: handler(r) if r.url.path.endswith("cafes.csv") else httpx.Response(404)
    )) as client:
        adapter_good, adapter_dead = _OneCandidateAdapter(good), _OneCandidateAdapter(dead)
        disc = DatasetDiscoveryEngine(adapters=[adapter_good, adapter_dead], http_client=client)
        async with maker() as session:
            candidates, imported = await disc.discover_and_process_datasets(
                session=session, study_id="st1", user_id="u1", run_id="run1",
                idea="Point-of-sale and card payment software for independent cafés in Lisbon",
                queries=_QUERIES, requirements=_REQS, countries=["PRT"],
            )
    assert adapter_good.received["countries"] == ["PRT"]
    assert len(imported) == 1 and imported[0].row_count == 30 and imported[0].column_count == 4
    assert imported[0].schema_metadata["is_sample"] is False
    assert imported[0].schema_metadata["fetched_from"] == "https://files.example.org/cafes.csv"
    assert "Fetched from: https://files.example.org/cafes.csv" in imported[0].description
    statuses = {c.external_id: c.selection_status for c in candidates}
    assert statuses["x"] == "imported"
    assert statuses["dead"] == "import_failed"
    dead_row = next(c for c in candidates if c.external_id == "dead")
    assert "HTTP 404" in dead_row.evaluation_details["import_error"]
    async with maker() as session:
        assert (await session.get(DatasetSources, imported[0].id)) is not None
        assert (await session.get(DatasetCandidates, candidates[0].id)) is not None
    get_settings.cache_clear()
