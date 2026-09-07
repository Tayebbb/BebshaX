"""Ollama discovery: an unreachable daemon is remembered for 30s.

Regression: every request whose pool includes the local adapter used to probe
/api/tags again while holding a pool semaphore slot — with the daemon down,
that is one wasted connection attempt per request, serialized under the
semaphore.
"""

import httpx

from bebshax.llm.adapters.ollama_adapter import NEGATIVE_DISCOVERY_TTL_S, OllamaAdapter


def _down_adapter(clock, probes: list[str]) -> OllamaAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        probes.append(request.url.path)
        raise httpx.ConnectError("refused", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ollama.t")
    return OllamaAdapter(client=client, base_url="http://ollama.t", tags_ttl=0.0, clock=clock)


async def test_two_calls_within_thirty_seconds_probe_once() -> None:
    now = {"t": 1_000.0}
    probes: list[str] = []
    adapter = _down_adapter(lambda: now["t"], probes)

    assert await adapter.candidates() == []
    now["t"] += 5.0
    assert await adapter.candidates() == []
    assert probes == ["/api/tags"]  # second call served from the negative cache


async def test_negative_cache_expires_and_reprobes() -> None:
    now = {"t": 0.0}
    probes: list[str] = []
    adapter = _down_adapter(lambda: now["t"], probes)

    await adapter.candidates()
    now["t"] += NEGATIVE_DISCOVERY_TTL_S + 0.5
    await adapter.candidates()
    assert probes == ["/api/tags", "/api/tags"]


async def test_recovered_daemon_clears_the_negative_result() -> None:
    now = {"t": 0.0}
    state = {"up": False}
    probes: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        probes.append(request.url.path)
        if not state["up"]:
            raise httpx.ConnectError("refused", request=request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "llama3.2:3b", "size": 2_000}]})
        return httpx.Response(200, json={"model_info": {"llama.context_length": 8192}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ollama.t")
    adapter = OllamaAdapter(
        client=client, base_url="http://ollama.t", tags_ttl=0.0, clock=lambda: now["t"]
    )

    assert await adapter.candidates() == []
    state["up"] = True
    assert await adapter.candidates() == []  # still inside the negative window — no probe
    assert probes == ["/api/tags"]

    now["t"] += NEGATIVE_DISCOVERY_TTL_S + 1
    cands = await adapter.candidates()
    assert [c.model for c in cands] == ["llama3.2:3b"]
    # a later failure re-arms the negative cache from scratch
    state["up"] = False
    now["t"] += 1
    assert await adapter.candidates() == []
    now["t"] += 1
    assert await adapter.candidates() == []
    assert probes.count("/api/tags") == 3
