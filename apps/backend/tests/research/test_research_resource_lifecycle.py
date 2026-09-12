import pytest

from bebshax.datasets.discovery.engine import DatasetDiscoveryEngine
from bebshax.research import service as research
from bebshax.research.vector_search import VectorSearchEngine


@pytest.mark.parametrize("borrowed", [False, True])
async def test_research_shutdown_closes_only_owned_search_clients(tmp_path, monkeypatch, borrowed):
    closed = []

    async def close():
        closed.append("search")

    provider = research.WikipediaResearchProvider()
    monkeypatch.setattr(provider, "aclose", close)
    monkeypatch.setattr(research, "_upload_dir", lambda: tmp_path)
    monkeypatch.setattr(research, "WikipediaResearchProvider", lambda: provider)
    service = research.ResearchEngineService(
        search_provider=provider if borrowed else None,
        vector_engine=VectorSearchEngine(), discovery_engine=DatasetDiscoveryEngine(adapters=[]),
    )
    await service.aclose()
    await service.aclose()
    assert closed == ([] if borrowed else ["search"])