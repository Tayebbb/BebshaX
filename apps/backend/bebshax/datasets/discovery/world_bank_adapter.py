"""World Bank Open Data adapter — live, keyless, country-driven.

Fetches real indicator series from https://api.worldbank.org/v2 for the study's
target countries (ISO-3166 alpha-3 codes chosen by the research plan). Which
indicators are pulled depends on the study's own queries and dataset
requirements. No country is assumed and there is no offline catalogue: when the
plan names no country or the API is unreachable the adapter returns nothing and
the run records that no dataset was found.
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
from typing import Optional

import httpx

from bebshax.datasets.discovery.base_adapter import DatasetCandidateData, DatasetSourceAdapter
from bebshax.research.planner import DatasetRequirementSpec
from bebshax.research.search_provider import query_tokens

logger = logging.getLogger(__name__)

WORLD_BANK_API_BASE = "https://api.worldbank.org/v2"
LIVE_DATE_RANGE = "2010:2024"
LIVE_TIMEOUT_SECONDS = 8.0
LIVE_SOURCE_LABEL = "World Bank Open Data"
LIVE_LICENSE = "CC BY-4.0 (World Bank Open Data terms of use)"
LIVE_LICENSE_URL = "https://datacatalog.worldbank.org/public-licenses"
MAX_COUNTRIES = 3
MAX_INDICATORS = 5
_ISO3 = re.compile(r"^[A-Z]{3}$")

# Data table: real World Bank indicator codes -> (display name, category, trigger tokens).
# Extend the table, not the code.
LIVE_INDICATORS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "FP.CPI.TOTL.ZG": ("Inflation, consumer prices (annual %)", "macro_prices",
                       ("price", "prices", "pricing", "cost", "inflation", "afford", "affordable", "spend", "spending", "budget", "subscription")),
    "NY.GDP.PCAP.CD": ("GDP per capita (current US$)", "macro_income",
                       ("income", "gdp", "purchasing", "afford", "economy", "revenue", "market", "wealth", "salary")),
    "IT.NET.USER.ZS": ("Individuals using the Internet (% of population)", "digital_adoption",
                       ("internet", "digital", "online", "app", "apps", "ecommerce", "commerce", "mobile", "tech", "software", "platform", "web")),
    "IT.CEL.SETS.P2": ("Mobile cellular subscriptions (per 100 people)", "digital_adoption",
                       ("mobile", "phone", "smartphone", "sms", "app", "apps", "telecom")),
    "SL.UEM.TOTL.ZS": ("Unemployment, total (% of total labor force)", "labor_market",
                       ("employment", "employ", "job", "jobs", "labor", "labour", "work", "worker", "workers", "career", "hiring")),
    "SP.POP.TOTL": ("Population, total", "demographics",
                    ("population", "people", "residents", "citizens", "demographic", "demographics", "market")),
    "SP.URB.TOTL.IN.ZS": ("Urban population (% of total population)", "demographics",
                          ("urban", "city", "cities", "metro", "town", "rural", "commute", "commuters")),
    "SE.TER.ENRR": ("School enrollment, tertiary (% gross)", "education",
                    ("student", "students", "university", "college", "education", "tertiary", "campus", "exam", "learning")),
    "SL.TLF.CACT.FE.ZS": ("Labor force participation rate, female (% of female population 15+)", "labor_market",
                          ("women", "female", "mothers", "gender")),
    "FB.ATM.TOTL.P5": ("Automated teller machines (per 100,000 adults)", "financial_access",
                       ("bank", "banking", "payment", "payments", "wallet", "fintech", "cash", "atm", "finance", "financial")),
    "EG.ELC.ACCS.ZS": ("Access to electricity (% of population)", "infrastructure",
                       ("electricity", "power", "energy", "grid", "solar", "appliance")),
    "SH.XPD.CHEX.PC.CD": ("Current health expenditure per capita (current US$)", "health",
                          ("health", "healthcare", "clinic", "medical", "patients", "wellness", "fitness", "pharmacy")),
    "IS.VEH.NVEH.P3": ("Motor vehicles (per 1,000 people)", "transport",
                       ("car", "cars", "vehicle", "vehicles", "transport", "ride", "delivery", "logistics", "commute")),
    "AG.LND.AGRI.ZS": ("Agricultural land (% of land area)", "agriculture",
                       ("farm", "farmers", "agriculture", "crop", "crops", "harvest", "food", "agri")),
}
# When the study text matches nothing specific, only macro context is offered —
# and it is labelled as context, not as a topical dataset.
_MACRO_CONTEXT = ("NY.GDP.PCAP.CD", "SP.POP.TOTL")


def live_indicator_url(code: str, country: str) -> str:
    """Real, keyless World Bank API URL for one indicator series of one country."""
    return f"{WORLD_BANK_API_BASE}/country/{country}/indicator/{code}?format=json&per_page=100&date={LIVE_DATE_RANGE}"


def select_indicators(study_text: str) -> tuple[list[str], bool]:
    """(indicator codes, topical) — codes whose trigger tokens appear as whole
    words in the study's own text; macro context otherwise (topical=False)."""
    tokens = query_tokens(study_text)
    scored = []
    for code, (_, _, triggers) in LIVE_INDICATORS.items():
        hits = sum(1 for t in triggers if t in tokens)
        if hits:
            scored.append((hits, code))
    if not scored:
        return list(_MACRO_CONTEXT), False
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [code for _, code in scored[:MAX_INDICATORS]], True


class WorldBankOpenDataAdapter(DatasetSourceAdapter):
    """World Bank Open Data source: live keyless API, target countries from the plan."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        # Injected client (tests use httpx.MockTransport); None -> real client per search.
        self._http_client = http_client

    @property
    def source_name(self) -> str:
        return LIVE_SOURCE_LABEL

    async def search(
        self,
        queries: list[str],
        requirements: list[DatasetRequirementSpec],
        *,
        countries: Optional[list[str]] = None,
    ) -> list[DatasetCandidateData]:
        iso3 = [c.upper() for c in (countries or []) if isinstance(c, str) and _ISO3.match(c.upper())][:MAX_COUNTRIES]
        if not iso3:
            logger.info("World Bank adapter skipped: the research plan named no target country")
            return []
        study_text = " ".join(queries) + " " + " ".join(f"{r.category} {r.description} {' '.join(r.target_variables)}" for r in requirements)
        codes, topical = select_indicators(study_text)
        try:
            if self._http_client is not None:
                return await self._fetch_all(self._http_client, iso3, codes, topical)
            async with httpx.AsyncClient(timeout=LIVE_TIMEOUT_SECONDS) as client:
                return await self._fetch_all(client, iso3, codes, topical)
        except Exception as exc:  # network failure -> no candidates, never a catalogue
            logger.info("World Bank live fetch failed: %s", type(exc).__name__)
            return []

    async def _fetch_all(
        self, client: httpx.AsyncClient, countries: list[str], codes: list[str], topical: bool
    ) -> list[DatasetCandidateData]:
        jobs = [(country, code) for country in countries for code in codes]
        results = await asyncio.gather(*(self._fetch_indicator(client, code, country, topical) for country, code in jobs), return_exceptions=True)
        candidates: list[DatasetCandidateData] = []
        for (country, code), result in zip(jobs, results):
            if isinstance(result, BaseException):
                logger.debug("World Bank %s/%s fetch failed: %s", country, code, result)
                continue
            if result is not None:
                candidates.append(result)
        return candidates

    async def _fetch_indicator(
        self, client: httpx.AsyncClient, code: str, country: str, topical: bool
    ) -> DatasetCandidateData | None:
        url = live_indicator_url(code, country)
        response = await client.get(url)
        response.raise_for_status()
        country_name, rows = self._parse_indicator_rows(response.json())
        if not rows:
            return None

        name, category, _ = LIVE_INDICATORS[code]
        label = country_name or country
        csv_content = self._rows_to_csv(label, code, name, rows)
        years = [year for year, _ in rows]
        context_note = "" if topical else " Offered as macro context: the study text matched no topical indicator."
        return DatasetCandidateData(
            source=LIVE_SOURCE_LABEL,
            external_id=f"worldbank-{country.lower()}-{code.lower().replace('.', '-')}",
            name=f"{name} — {label}",
            description=(
                f"Official World Bank Open Data series {code} for {label}, fetched live from the free keyless "
                f"api.worldbank.org API ({years[0]}–{years[-1]}, {len(rows)} annual observations).{context_note}"
            ),
            url=f"https://data.worldbank.org/indicator/{code}?locations={country}",
            download_url=url,
            publisher=LIVE_SOURCE_LABEL,
            license=LIVE_LICENSE,
            license_url=LIVE_LICENSE_URL,
            format="csv",
            size_bytes=len(csv_content.encode("utf-8")),
            sample_rows=len(rows),
            sample_columns=5,
            geographic_coverage=label,
            population_coverage="National population",
            relevant_variables=["year", "value", code],
            category=category if topical else "macro_context",
            tags=[category, "world-bank", code],
            modified_at=None,
            is_sample=False,
            raw_data_content=csv_content,
        )

    @staticmethod
    def _parse_indicator_rows(payload: object) -> tuple[str, list[tuple[str, float]]]:
        """(country name, [(year, value)]) from the World Bank [metadata, rows] envelope."""
        if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
            return "", []
        rows: list[tuple[str, float]] = []
        country_name = ""
        for entry in payload[1]:
            if not isinstance(entry, dict):
                continue
            if not country_name:
                country_name = str((entry.get("country") or {}).get("value") or "")
            value = entry.get("value")
            year = entry.get("date")
            if value is None or not isinstance(year, str) or not year:
                continue
            try:
                rows.append((year, float(value)))
            except (TypeError, ValueError):
                continue
        rows.sort(key=lambda pair: pair[0])
        return country_name, rows

    @staticmethod
    def _rows_to_csv(country: str, code: str, indicator_name: str, rows: list[tuple[str, float]]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["country", "indicator_code", "indicator_name", "year", "value"])
        for year, value in rows:
            writer.writerow([country, code, indicator_name, year, value])
        return buffer.getvalue()
