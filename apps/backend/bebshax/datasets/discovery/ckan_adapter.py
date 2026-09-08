"""CKAN open-data portal adapter — live, keyless catalogue search.

CKAN powers many public data portals; the ``package_search`` action is public
and needs no key. Two portals are wired by default because they are global,
stable and licence-labelled:

* Humanitarian Data Exchange (HDX) — https://data.humdata.org
* data.gov (US federal catalogue)  — https://catalog.data.gov

Each candidate is a dataset that really exists there, with its published
title, notes, organisation, licence, tags, timestamps and a direct CSV/JSON
resource URL when one is listed. Nothing is served when the portal is
unreachable or finds nothing.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx

from bebshax.datasets.discovery.base_adapter import DatasetCandidateData, DatasetSourceAdapter
from bebshax.research.planner import DatasetRequirementSpec
from bebshax.research.search_provider import query_tokens

logger = logging.getLogger(__name__)

CKAN_TIMEOUT_SECONDS = 8.0
CKAN_MAX_QUERIES = 3
CKAN_ROWS_PER_QUERY = 5
_TABULAR_FORMATS = {"csv": "csv", "json": "json", "tsv": "tsv", "xlsx": "xlsx", "xls": "xlsx", "geojson": None, "zipped csv": None}
_USER_AGENT = "BebshaX/0.1 (dataset discovery; https://github.com/Tayebbb/BebshaX)"


class CKANDatasetAdapter(DatasetSourceAdapter):
    """One CKAN portal. Use the ``hdx()`` / ``datagov()`` constructors for the defaults."""

    def __init__(
        self,
        base_url: str,
        label: str,
        *,
        dataset_path: str = "/dataset/",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.label = label
        self.dataset_path = dataset_path
        self._http_client = http_client

    @classmethod
    def hdx(cls, http_client: httpx.AsyncClient | None = None) -> "CKANDatasetAdapter":
        return cls("https://data.humdata.org", "Humanitarian Data Exchange (HDX)", http_client=http_client)

    @classmethod
    def datagov(cls, http_client: httpx.AsyncClient | None = None) -> "CKANDatasetAdapter":
        return cls("https://catalog.data.gov", "data.gov", http_client=http_client)

    @property
    def source_name(self) -> str:
        return self.label

    async def search(
        self,
        queries: list[str],
        requirements: list[DatasetRequirementSpec],
        *,
        countries: Optional[list[str]] = None,
    ) -> list[DatasetCandidateData]:
        # Queries are the study's own (model-written) search phrases; the
        # requirement categories add the plan's dataset vocabulary.
        terms = [q.strip() for q in queries if q and q.strip()][:CKAN_MAX_QUERIES]
        for req in requirements:
            if len(terms) >= CKAN_MAX_QUERIES + 2:
                break
            phrase = " ".join(sorted(query_tokens(req.category.replace("_", " ") + " " + req.description))[:6])
            if phrase and phrase not in terms:
                terms.append(phrase)
        if not terms:
            return []
        try:
            if self._http_client is not None:
                return await self._search_all(self._http_client, terms)
            async with httpx.AsyncClient(
                timeout=CKAN_TIMEOUT_SECONDS, headers={"User-Agent": _USER_AGENT}, follow_redirects=False
            ) as client:
                return await self._search_all(client, terms)
        except Exception as exc:  # portal down -> nothing, never a catalogue
            logger.info("%s search failed: %s", self.label, type(exc).__name__)
            return []

    async def _search_all(self, client: httpx.AsyncClient, terms: list[str]) -> list[DatasetCandidateData]:
        results = await asyncio.gather(*(self._search_one(client, t) for t in terms), return_exceptions=True)
        seen: set[str] = set()
        out: list[DatasetCandidateData] = []
        for term, result in zip(terms, results):
            if isinstance(result, BaseException):
                logger.debug("%s query %r failed: %s", self.label, term, result)
                continue
            for cand in result:
                if cand.external_id in seen:
                    continue
                seen.add(cand.external_id)
                out.append(cand)
        return out

    async def _search_one(self, client: httpx.AsyncClient, term: str) -> list[DatasetCandidateData]:
        response = await client.get(
            f"{self.base_url}/api/3/action/package_search",
            params={"q": term, "rows": CKAN_ROWS_PER_QUERY, "sort": "score desc, metadata_modified desc"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("success"):
            return []
        packages = (payload.get("result") or {}).get("results") or []
        return [c for c in (self._to_candidate(p) for p in packages if isinstance(p, dict)) if c is not None]

    def _to_candidate(self, pkg: dict[str, Any]) -> DatasetCandidateData | None:
        name = str(pkg.get("title") or pkg.get("name") or "").strip()
        slug = str(pkg.get("name") or pkg.get("id") or "").strip()
        if not name or not slug:
            return None
        resource = self._pick_resource(pkg.get("resources") or [])
        org = pkg.get("organization") or {}
        publisher = str(org.get("title") or pkg.get("dataset_source") or pkg.get("maintainer") or self.label).strip()
        tags = [str(t.get("name") or t.get("display_name") or "") for t in (pkg.get("tags") or []) if isinstance(t, dict)]
        tags = [t for t in tags if t]
        groups = [str(g.get("title") or g.get("display_name") or g.get("name") or "") for g in (pkg.get("groups") or []) if isinstance(g, dict)]
        size = resource.get("size") if resource else None
        try:
            size_bytes = int(size) if size not in (None, "", 0, "0") else None
        except (TypeError, ValueError):
            size_bytes = None
        return DatasetCandidateData(
            source=self.label,
            external_id=f"{self.base_url}#{slug}",
            name=name,
            description=" ".join(str(pkg.get("notes") or "").split())[:1200],
            url=f"{self.base_url}{self.dataset_path}{slug}",
            download_url=str(resource.get("url")) if resource and resource.get("url") else None,
            publisher=publisher or self.label,
            license=str(pkg.get("license_title") or pkg.get("license_id") or "").strip(),
            license_url=str(pkg.get("license_url") or "") or None,
            format=(resource or {}).get("_format", "csv"),
            size_bytes=size_bytes,
            sample_rows=None,
            sample_columns=None,
            geographic_coverage=", ".join(g for g in groups if g)[:256],
            population_coverage="",
            relevant_variables=tags[:12],
            category=str((pkg.get("groups") or [{}])[0].get("name") or "general") if pkg.get("groups") else "general",
            tags=tags[:20],
            modified_at=str(pkg.get("metadata_modified") or "") or None,
            is_sample=False,
            raw_data_content=None,
        )

    @staticmethod
    def _pick_resource(resources: list[Any]) -> dict[str, Any] | None:
        """The first tabular resource with a URL (CSV preferred)."""
        best: dict[str, Any] | None = None
        best_rank = 99
        rank = {"csv": 0, "tsv": 1, "json": 2, "xlsx": 3}
        for res in resources:
            if not isinstance(res, dict) or not res.get("url"):
                continue
            fmt = str(res.get("format") or "").strip().lower()
            mapped = _TABULAR_FORMATS.get(fmt)
            if mapped is None:
                continue
            r = rank.get(mapped, 9)
            if r < best_rank:
                best, best_rank = {**res, "_format": mapped}, r
        return best
