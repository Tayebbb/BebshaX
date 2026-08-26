"""H2 regression: losing the local Ollama tier must be loud at startup.

The emergency pool is local-FIRST; a dead daemon means EMERGENCY_FALLBACK has
no route at all, which the 2026-08-24 audit found failing silently.
"""

import logging

import pytest

from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.main import warn_if_local_tier_down


@pytest.mark.asyncio
async def test_warns_when_ollama_has_no_routes(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="bebshax.main"):
        up = await warn_if_local_tier_down({"ollama": FakeAdapter([])})
    assert up is False
    assert any("local tier DOWN" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_warns_when_ollama_adapter_missing(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="bebshax.main"):
        up = await warn_if_local_tier_down({})
    assert up is False
    assert any("no 'ollama' adapter" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_warns_when_candidate_discovery_raises(caplog) -> None:
    class ExplodingAdapter(FakeAdapter):
        async def candidates(self):
            raise RuntimeError("boom")

    with caplog.at_level(logging.WARNING, logger="bebshax.main"):
        up = await warn_if_local_tier_down({"ollama": ExplodingAdapter([])})
    assert up is False
    assert any("candidate discovery failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_quiet_when_local_tier_up(caplog) -> None:
    adapter = FakeAdapter(
        [FakeRoute(candidate=RouteCandidate(provider="ollama", model="llama3.2:3b"))]
    )
    with caplog.at_level(logging.WARNING, logger="bebshax.main"):
        up = await warn_if_local_tier_down({"ollama": adapter})
    assert up is True
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
