"""Evidence source providers and deterministic deduplication.

Live evidence comes from a keyless, fixed-host provider (Wikipedia) with real
URLs, publisher, licence and a COMPUTED relevance score. There is no curated
corpus in the live path: when nothing can be retrieved the run says so
(``no_live_evidence``) instead of serving the same hand-written documents to
every study. A sample provider exists for unit tests only and must be enabled
explicitly.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredSource:
    title: str
    url: str
    publisher: str
    source_type: str  # web, reddit, review, report, upload
    content: str
    content_hash: str
    relevance_score: float = 0.0  # providers must set explicitly; 0.0 fails loudly if forgotten
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_url(raw_url: str) -> str:
    """Normalize URL by standardizing scheme to https, stripping tracking params and trailing slashes."""
    try:
        parsed = urlparse(raw_url.strip())
        scheme = "https"
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parsed.path.rstrip("/")
        # Filter query params
        query_parts = []
        if parsed.query:
            for param in parsed.query.split("&"):
                k = param.split("=")[0].lower()
                if not (k.startswith("utm_") or k in ("ref", "source", "fbclid", "gclid")):
                    query_parts.append(param)
        clean_query = "&".join(query_parts)
        return urlunparse((scheme, netloc, path, "", clean_query, ""))
    except Exception:
        # Deliberate swallow: URL normalization is best-effort string hygiene;
        # an unparseable URL is still a usable dedup key as-is.
        return raw_url.strip().lower()


def compute_content_hash(content: str) -> str:
    """Compute sha256 hex digest of normalized content."""
    normalized = " ".join(content.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def extract_publisher(url: str, default: str = "Web Source") -> str:
    """Registrable domain of a URL as a neutral publisher label (never a guessed outlet name)."""
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc or default
    except Exception:
        # Deliberate swallow: publisher extraction is cosmetic labeling;
        # a malformed URL simply gets the generic default label.
        return default


_TOKEN_RE = re.compile(r"[^\W_]{3,}", re.UNICODE)
_QUERY_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "that", "this", "from", "into", "about", "what", "how",
        "why", "who", "are", "was", "were", "you", "your", "our", "their", "they", "them",
        "does", "did", "will", "would", "should", "could", "than", "then", "there", "here",
        "have", "has", "had", "not", "but", "also", "its", "per", "via", "use", "using",
    }
)


def query_tokens(text: str) -> set[str]:
    """Lower-cased content tokens (≥3 chars, Unicode-aware, stopwords removed)."""
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if t.lower() not in _QUERY_STOPWORDS}


def lexical_relevance(query_text: str, document_text: str) -> float:
    """Computed overlap 0–1: share of the query's content tokens present in the
    document (with a small weight for how much of the document they cover).
    Never floored — an unrelated document scores ~0.0."""
    q = query_tokens(query_text)
    d = query_tokens(document_text)
    if not q or not d:
        return 0.0
    hit = len(q & d)
    recall = hit / len(q)
    density = hit / len(d)
    return round(min(1.0, 0.85 * recall + 0.15 * min(1.0, density * 10)), 3)


class SearchProvider(ABC):
    @property
    def name(self) -> str:
        """Human-readable provider label recorded on each research run."""
        return type(self).__name__

    @abstractmethod
    async def search(self, queries: list[str], max_results_per_query: int = 4) -> list[DiscoveredSource]:
        """Search for relevant sources matching queries and return deduplicated results."""


# ---------------------------------------------------------------------------
# Live, keyless provider — Wikipedia (fixed host: no user-controlled URL,
# hence no SSRF surface; CC BY-SA 4.0 content; a descriptive User-Agent as
# the Wikimedia API etiquette requires).
# ---------------------------------------------------------------------------

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
WIKIPEDIA_LICENSE = "CC BY-SA 4.0"
_USER_AGENT = "BebshaX/0.1 (synthetic-persona research tool; https://github.com/Tayebbb/BebshaX)"

# Budget table (data, not branches): keep a research run's evidence step bounded
# on a slow venue network.
WIKI_MAX_QUERIES = 6
WIKI_PAGES_PER_QUERY = 3
WIKI_PER_REQUEST_TIMEOUT_S = 8.0
WIKI_TOTAL_BUDGET_S = 40.0
WIKI_MIN_RELEVANCE = 0.08  # below this the page shares almost nothing with the query


class WikipediaResearchProvider(SearchProvider):
    """Live evidence from Wikipedia search + page summaries.

    Every source carries a real URL, publisher "Wikipedia", the CC BY-SA licence
    and a COMPUTED relevance score. Network or API failure yields an empty list
    (the caller records ``no_live_evidence``) — never canned documents.
    """

    def __init__(self, http_client: Optional[Any] = None) -> None:
        # Injected client for tests (httpx.MockTransport); created lazily otherwise.
        self._client = http_client
        self._owns_client = http_client is None

    async def _get_client(self) -> Any:
        if self._client is None:
            import httpx  # local import keeps module import cheap for non-research paths

            self._client = httpx.AsyncClient(
                timeout=WIKI_PER_REQUEST_TIMEOUT_S,
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
                follow_redirects=False,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def _search_titles(self, client: Any, query: str, limit: int) -> list[str]:
        response = await client.get(
            WIKIPEDIA_API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": limit,
                "srprop": "",
            },
        )
        response.raise_for_status()
        payload = response.json()
        hits = payload.get("query", {}).get("search", []) if isinstance(payload, dict) else []
        return [str(h.get("title")) for h in hits if isinstance(h, dict) and h.get("title")]

    async def _summary(self, client: Any, title: str) -> Optional[dict[str, Any]]:
        from urllib.parse import quote

        response = await client.get(WIKIPEDIA_SUMMARY + quote(title.replace(" ", "_"), safe=""))
        if response.status_code != 200:
            return None
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("type") == "disambiguation":
            return None
        extract = str(payload.get("extract") or "").strip()
        if len(extract) < 80:
            return None
        url = (payload.get("content_urls") or {}).get("desktop", {}).get("page") or (
            f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
        )
        return {
            "title": str(payload.get("title") or title),
            "url": url,
            "extract": extract,
            "description": str(payload.get("description") or ""),
            "revision": str(payload.get("revision") or ""),
            "timestamp": str(payload.get("timestamp") or ""),
        }

    async def _one_query(self, client: Any, query: str, limit: int) -> list[tuple[str, dict[str, Any]]]:
        titles = await self._search_titles(client, query, limit)
        summaries = await asyncio.gather(*(self._summary(client, t) for t in titles), return_exceptions=True)
        out: list[tuple[str, dict[str, Any]]] = []
        for item in summaries:
            if isinstance(item, dict):
                out.append((query, item))
        return out

    async def search(self, queries: list[str], max_results_per_query: int = 4) -> list[DiscoveredSource]:
        queries = [q.strip() for q in queries if q and q.strip()][:WIKI_MAX_QUERIES]
        if not queries:
            return []
        limit = max(1, min(max_results_per_query, WIKI_PAGES_PER_QUERY))
        client = await self._get_client()
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*(self._one_query(client, q, limit) for q in queries), return_exceptions=True),
                timeout=WIKI_TOTAL_BUDGET_S,
            )
        except asyncio.TimeoutError:
            logger.warning("wikipedia evidence search exceeded the %.0fs budget", WIKI_TOTAL_BUDGET_S)
            return []
        except Exception:  # network/DNS/TLS: an explicit empty result, never canned docs
            logger.warning("wikipedia evidence search failed", exc_info=True)
            return []

        query_blob = " ".join(queries)
        discovered: list[DiscoveredSource] = []
        seen_urls: set[str] = set()
        seen_hashes: set[str] = set()
        for group in results:
            if not isinstance(group, list):
                continue
            for query, page in group:
                canonical_url = normalize_url(page["url"])
                chash = compute_content_hash(page["extract"])
                if canonical_url in seen_urls or chash in seen_hashes:
                    continue
                relevance = max(
                    lexical_relevance(query, page["title"] + " " + page["extract"]),
                    lexical_relevance(query_blob, page["title"] + " " + page["extract"]),
                )
                if relevance < WIKI_MIN_RELEVANCE:
                    continue
                seen_urls.add(canonical_url)
                seen_hashes.add(chash)
                discovered.append(
                    DiscoveredSource(
                        title=page["title"],
                        url=canonical_url,
                        publisher="Wikipedia",
                        source_type="web",
                        content=page["extract"],
                        content_hash=chash,
                        relevance_score=relevance,
                        metadata={
                            "query": query,
                            "license": WIKIPEDIA_LICENSE,
                            "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                            "description": page["description"],
                            "revision": page["revision"],
                            "retrieved_via": "wikipedia_api",
                            "is_sample": False,
                        },
                    )
                )
        discovered.sort(key=lambda s: s.relevance_score, reverse=True)
        return discovered


# ---------------------------------------------------------------------------
# Test-only provider — never selected by default, always labelled a sample.
# ---------------------------------------------------------------------------

ILLUSTRATIVE_SOURCE_PUBLISHER = "BebshaX Illustrative Sample"


class IllustrativeSampleProvider(SearchProvider):
    """Deterministic documents for unit tests of the evidence pipeline.

    Construction requires ``allow_sample=True`` so it can never be wired by
    accident; every source is ``source_type="curated_sample"`` with
    ``is_sample=True`` and the publisher label above.
    """

    def __init__(self, documents: list[dict[str, Any]], *, allow_sample: bool = False) -> None:
        if not allow_sample:
            raise ValueError("IllustrativeSampleProvider is for tests only — pass allow_sample=True explicitly")
        self.documents = documents

    async def search(self, queries: list[str], max_results_per_query: int = 4) -> list[DiscoveredSource]:
        blob = " ".join(queries)
        out: list[DiscoveredSource] = []
        for doc in self.documents:
            out.append(
                DiscoveredSource(
                    title=doc["title"],
                    url=normalize_url(doc["url"]),
                    publisher=ILLUSTRATIVE_SOURCE_PUBLISHER,
                    source_type="curated_sample",
                    content=doc["content"],
                    content_hash=compute_content_hash(doc["content"]),
                    relevance_score=lexical_relevance(blob, doc["title"] + " " + doc["content"]),
                    metadata={"is_sample": True, "license": "sample"},
                )
            )
        out.sort(key=lambda s: s.relevance_score, reverse=True)
        return out
