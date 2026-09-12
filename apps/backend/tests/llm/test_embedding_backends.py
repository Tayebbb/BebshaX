"""Embedding cutover preserves the hash space and rejects retired auto backends."""

import asyncio
import threading
from pathlib import Path
from contextvars import Context
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from types import SimpleNamespace

import httpx
import pytest
from freellmpool import config as fl_config
from freellmpool.errors import AllProvidersExhausted
from freellmpool.models import Model, Provider

from bebshax.llm.adapters.embeddings import CANONICAL_DIM, FreellmpoolEmbedding, HashEmbedding
from bebshax.llm.adapters.factory import build_embedding_backend
from bebshax.llm.governance import LLMRequestContext, RemoteProcessingPolicy, llm_request_context


@pytest.fixture(autouse=True)
async def trusted_synthetic_embedding_request() -> AsyncIterator[None]:
    with llm_request_context(LLMRequestContext(data_classification="synthetic")):
        yield


@pytest.fixture
def approved_embedding_policy() -> RemoteProcessingPolicy:
    return RemoteProcessingPolicy(
        policy_id="reviewed-synthetic-embedding",
        synthetic_providers=frozenset({"freellmpool", "approved-remote"}),
    )


async def test_hash_vectors_keep_their_canonical_dimension_and_normalization() -> None:
    backend = build_embedding_backend("local")
    vectors = await backend.embed(["complete source text", "another source text"])
    assert len(vectors) == 2
    assert all(len(vector) == CANONICAL_DIM for vector in vectors)
    assert all(sum(value * value for value in vector) == pytest.approx(1.0) for vector in vectors)
    assert backend.space == "local-hash-384"


async def test_hash_embedding_is_deterministic_across_instances() -> None:
    assert await HashEmbedding().embed(["same complete text"]) == await build_embedding_backend().embed(["same complete text"])


@pytest.mark.parametrize("backend", ["auto", "ollama", "banana"])
def test_retired_or_unknown_embedding_backend_is_explicitly_rejected(backend) -> None:
    with pytest.raises(ValueError, match="expected 'local' or 'freellmpool'"):
        build_embedding_backend(backend)


def test_remote_embeddings_require_a_pinned_model(approved_embedding_policy: RemoteProcessingPolicy) -> None:
    with pytest.raises(ValueError, match="BEBSHAX_EMBEDDING_MODEL"):
        build_embedding_backend("freellmpool")
    backend = build_embedding_backend(
        "freellmpool", model="verified-embedding-model", processing_policy=approved_embedding_policy,
    )
    assert isinstance(backend, FreellmpoolEmbedding)


@pytest.mark.parametrize("policy_options", [{}, {"processing_policy": None}], ids=["omitted", "none"])
def test_remote_embedding_requires_processing_policy_before_catalog_or_http(
    policy_options: dict[str, None], monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args, **kwargs) -> None:
        pytest.fail("Missing processing policy must be rejected before catalog or HTTP client construction")

    monkeypatch.setattr(fl_config, "load_catalog", forbidden)
    monkeypatch.setattr(httpx, "Client", forbidden)

    with pytest.raises(ValueError, match="(?i)processing policy"):
        FreellmpoolEmbedding("verified-embedding-model", **policy_options)


async def test_explicit_embedding_policy_only_dispatches_to_approved_remote_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, approved_embedding_policy: RemoteProcessingPolicy,
) -> None:
    policy_path = tmp_path / "embedding-providers.toml"
    policy_path.write_text("", encoding="utf-8")
    catalog = [
        Provider(
            id=provider_id, label=provider_id, adapter="openai", base_url=url,
            auth="none", models=(Model(name="verified-embedding-model", context=8192),),
        )
        for provider_id, url in [
            ("approved-remote", "https://embedding.example.com/v1"),
            ("ollama", "http://localhost:11434/v1"),
            ("ollama-cloud", "https://ollama.com/v1"),
            ("openrouter", "https://openrouter.ai/api/v1"),
            ("unapproved-local", "https://127.0.0.1/v1"),
        ]
    ]
    loaded_paths: list[Path] = []
    dispatched: list[list[str]] = []

    def load_catalog(path: Path) -> list[Provider]:
        loaded_paths.append(path)
        return catalog if path == policy_path else []

    class PolicyPool:
        def __init__(self, providers: list[Provider], **options) -> None:
            self.providers = providers

        @classmethod
        def from_default_config(cls):
            pytest.fail("Remote embeddings must never load unrestricted SDK defaults")

        def embed(self, texts: list[str], *, model: str, **options):
            dispatched.append([provider.id for provider in self.providers])
            assert texts == ["Full source identity and evidence " * 200]
            assert model == "verified-embedding-model"
            return SimpleNamespace(
                vectors=[[1.0] + [0.0] * (CANONICAL_DIM - 1)],
                provider_id="approved-remote", model=model,
            )

    monkeypatch.setattr(fl_config, "load_catalog", load_catalog)
    monkeypatch.setattr("freellmpool.Pool", PolicyPool)
    backend = build_embedding_backend(
        "freellmpool", model="verified-embedding-model", provider_config=policy_path,
        processing_policy=approved_embedding_policy,
    )

    vectors = await backend.embed(["Full source identity and evidence " * 200])

    assert policy_path in loaded_paths
    assert dispatched == [["approved-remote"]]
    assert len(vectors[0]) == CANONICAL_DIM
    assert backend.space == "freellmpool:approved-remote:verified-embedding-model:native-384"


@pytest.mark.parametrize("contents", [None, "invalid = ["])
async def test_unknown_embedding_policy_fails_closed_before_pool_construction(
    contents: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    approved_embedding_policy: RemoteProcessingPolicy,
) -> None:
    policy_path = tmp_path / "unknown-providers.toml"
    if contents is not None:
        policy_path.write_text(contents, encoding="utf-8")

    class ForbiddenPool:
        def __init__(self, *args, **kwargs) -> None:
            pytest.fail("Invalid embedding policy must fail before constructing a pool")

        @classmethod
        def from_default_config(cls):
            pytest.fail("Invalid embedding policy must not fall back to SDK defaults")

    monkeypatch.setattr("freellmpool.Pool", ForbiddenPool)

    with pytest.raises(ValueError, match="(?i)(policy|catalog|configuration)"):
        backend = build_embedding_backend(
            "freellmpool", model="verified-embedding-model", provider_config=policy_path,
            processing_policy=approved_embedding_policy,
        )
        await backend.embed(["Private complete evidence"])


@pytest.fixture
def embedding_catalog(tmp_path: Path) -> Path:
    policy_path = tmp_path / "providers.toml"
    policy_path.write_text(
        '[[provider]]\nid="approved-remote"\n'
        'base_url="https://embedding.example.com/v1"\nauth="none"\n'
        '[[provider.models]]\nname="verified-embedding-model"\ncontext=131072\n',
        encoding="utf-8",
    )
    return policy_path


def embedding_response(vectors: list[list[float]], *, model: str = "verified-embedding-model") -> httpx.Response:
    return httpx.Response(200, json={
        "model": model,
        "data": [{"index": index, "embedding": vector} for index, vector in enumerate(vectors)],
    })


@pytest.mark.parametrize(
    "synthetic_providers",
    [
        frozenset(),
        frozenset({"freellmpool"}),
        frozenset({"approved-remote"}),
        frozenset({"freellmpool", "another-remote"}),
    ],
    ids=["empty-policy", "adapter-only", "destination-only", "different-destination"],
)
async def test_remote_embedding_does_not_infer_processing_approval_from_catalog(
    embedding_catalog: Path, synthetic_providers: frozenset[str],
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return embedding_response([[1.0] + [0.0] * (CANONICAL_DIM - 1)])

    backend = FreellmpoolEmbedding(
        "verified-embedding-model", provider_config=embedding_catalog,
        processing_policy=RemoteProcessingPolicy(synthetic_providers=synthetic_providers),
        transport=httpx.MockTransport(respond),
    )
    try:
        with pytest.raises(ValueError, match="destination is not approved"):
            await backend.embed(["Complete synthetic source evidence"])
        assert calls == []
    finally:
        await backend.aclose()


async def test_empty_remote_embedding_batch_never_discovers_or_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_load(*args):
        pytest.fail("An empty embedding batch must not create a remote pool")

    monkeypatch.setattr(fl_config, "load_catalog", forbidden_load)
    backend = FreellmpoolEmbedding("verified-embedding-model", processing_policy=RemoteProcessingPolicy())
    assert await backend.embed([]) == []


@pytest.mark.parametrize("vector", [[1.0] * 383, [1.0] * 385, [0.0] * 384, [True] * 384])
async def test_remote_embedding_rejects_invalid_native_vectors_instead_of_resizing(
    embedding_catalog: Path, vector: list[float], approved_embedding_policy: RemoteProcessingPolicy,
) -> None:
    backend = FreellmpoolEmbedding(
        "verified-embedding-model", provider_config=embedding_catalog,
        processing_policy=approved_embedding_policy,
        transport=httpx.MockTransport(lambda request: embedding_response([vector])),
    )
    try:
        with pytest.raises(ValueError, match="(?i)(dimension|vector)"):
            await backend.embed(["Complete evidence"])
    finally:
        await backend.aclose()


async def test_native_remote_embedding_space_is_versioned_and_keeps_input_order(
    embedding_catalog: Path, approved_embedding_policy: RemoteProcessingPolicy,
) -> None:
    full_text = "Complete source identity and evidence " * 500
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        import json

        calls.append(request)
        assert json.loads(request.content)["input"] == [full_text, "Second source"]
        return httpx.Response(200, json={
            "model": "verified-embedding-model",
            "data": [
                {"index": 1, "embedding": [0.0, 2.0] + [0.0] * 382},
                {"index": 0, "embedding": [2.0] + [0.0] * 383},
            ],
        })

    backend = FreellmpoolEmbedding(
        "verified-embedding-model", provider_config=embedding_catalog,
        processing_policy=approved_embedding_policy,
        transport=httpx.MockTransport(respond),
    )
    try:
        vectors = await backend.embed([full_text, "Second source"])
        assert vectors[0] == [1.0] + [0.0] * 383
        assert vectors[1] == [0.0, 1.0] + [0.0] * 382
        assert backend.space == "freellmpool:approved-remote:verified-embedding-model:native-384"
        assert [str(call.url) for call in calls] == ["https://embedding.example.com/v1/embeddings"]
    finally:
        await backend.aclose()


async def test_remote_embedding_response_cannot_silently_substitute_a_model(
    embedding_catalog: Path, approved_embedding_policy: RemoteProcessingPolicy,
) -> None:
    backend = FreellmpoolEmbedding(
        "verified-embedding-model", provider_config=embedding_catalog,
        processing_policy=approved_embedding_policy,
        transport=httpx.MockTransport(lambda request: embedding_response([[1.0] * 384], model="different-space")),
    )
    try:
        with pytest.raises((ValueError, AllProvidersExhausted), match="(?i)(model|space)"):
            await backend.embed(["Complete evidence"])
    finally:
        await backend.aclose()


async def test_remote_embedding_redirect_cannot_disclose_input_to_another_destination(
    embedding_catalog: Path, approved_embedding_policy: RemoteProcessingPolicy,
) -> None:
    calls: list[str] = []

    def redirect(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(307, headers={"Location": "https://unapproved.example.com/embeddings"})

    backend = FreellmpoolEmbedding(
        "verified-embedding-model", provider_config=embedding_catalog, transport=httpx.MockTransport(redirect),
        processing_policy=approved_embedding_policy,
    )
    try:
        with pytest.raises(AllProvidersExhausted):
            await backend.embed(["Complete evidence"])
        assert calls == ["https://embedding.example.com/v1/embeddings"]
    finally:
        await backend.aclose()


@pytest.mark.parametrize("replacement", ['name="different-model"', 'name="openrouter/free"'])
async def test_embedding_policy_with_no_pinned_approved_model_fails_before_http(
    embedding_catalog: Path, replacement: str, approved_embedding_policy: RemoteProcessingPolicy,
) -> None:
    embedding_catalog.write_text(
        embedding_catalog.read_text(encoding="utf-8").replace('name="verified-embedding-model"', replacement),
        encoding="utf-8",
    )

    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("An unknown or excluded embedding model must never reach transport")

    backend = FreellmpoolEmbedding(
        "verified-embedding-model", provider_config=embedding_catalog, transport=httpx.MockTransport(forbidden),
        processing_policy=approved_embedding_policy,
    )
    try:
        with pytest.raises(ValueError, match="(?i)(policy|pinned|approved)"):
            await backend.embed(["Complete evidence"])
    finally:
        await backend.aclose()


async def test_embedding_cancellation_retains_worker_ownership_and_close_waits_for_it(
    embedding_catalog: Path, approved_embedding_policy: RemoteProcessingPolicy,
) -> None:
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()
    transport_closed = threading.Event()
    calls: list[str] = []

    class BlockingTransport(httpx.MockTransport):
        def close(self) -> None:
            transport_closed.set()
            super().close()

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(timeout=3), "The test must release its embedding worker"
        return embedding_response([[1.0] + [0.0] * 383])

    backend = FreellmpoolEmbedding(
        "verified-embedding-model", provider_config=embedding_catalog, transport=BlockingTransport(respond),
        processing_policy=approved_embedding_policy,
    )
    running = asyncio.create_task(backend.embed(["First complete source"]))
    queued = None
    closing = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        queued = asyncio.create_task(backend.embed(["Cancelled queued source"]))
        await asyncio.sleep(0)
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
        closing = asyncio.create_task(backend.aclose())
        await asyncio.sleep(0)
        assert not closing.done()
        assert not transport_closed.is_set()
        release.set()
        await asyncio.wait_for(closing, timeout=1)
        assert len(calls) == 1
        assert transport_closed.is_set()
        with pytest.raises(RuntimeError, match="closed"):
            await backend.embed(["Source after close"])
    finally:
        release.set()
        await asyncio.gather(running, *([queued] if queued is not None else []), return_exceptions=True)
        if closing is not None:
            await closing
        await backend.aclose()


def test_unmanaged_embedding_pool_injection_cannot_bypass_provider_policy(
    approved_embedding_policy: RemoteProcessingPolicy,
) -> None:
    with pytest.raises(ValueError, match="(?i)(unmanaged|transport|policy)"):
        FreellmpoolEmbedding(
            "verified-embedding-model", pool=SimpleNamespace(), processing_policy=approved_embedding_policy,
        )


@pytest.mark.parametrize("context", ["", "context=0\n", "context=8\n"])
async def test_embedding_context_is_verified_and_full_input_must_fit_before_http(
    embedding_catalog: Path, context: str, approved_embedding_policy: RemoteProcessingPolicy,
) -> None:
    embedding_catalog.write_text(
        embedding_catalog.read_text(encoding="utf-8").replace("context=131072\n", context), encoding="utf-8",
    )
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return embedding_response([[1.0] * 384])

    backend = FreellmpoolEmbedding(
        "verified-embedding-model", provider_config=embedding_catalog, transport=httpx.MockTransport(respond),
        processing_policy=approved_embedding_policy,
    )
    try:
        with pytest.raises(ValueError, match="(?i)context"):
            await backend.embed(["Complete source evidence must never be truncated " * 100])
        assert not calls
    finally:
        await backend.aclose()


async def test_duplicate_embedding_model_alias_across_providers_is_not_one_space(
    embedding_catalog: Path, approved_embedding_policy: RemoteProcessingPolicy,
) -> None:
    original = embedding_catalog.read_text(encoding="utf-8")
    embedding_catalog.write_text(
        original + original.replace('id="approved-remote"', 'id="another-approved-remote"'), encoding="utf-8",
    )
    backend = FreellmpoolEmbedding(
        "verified-embedding-model", provider_config=embedding_catalog, processing_policy=approved_embedding_policy,
    )
    try:
        with pytest.raises(ValueError, match="exactly one"):
            await backend.embed(["Complete source"])
    finally:
        await backend.aclose()


async def test_embedding_deadline_does_not_release_worker_or_allow_queued_http(
    embedding_catalog: Path, approved_embedding_policy: RemoteProcessingPolicy,
) -> None:
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(timeout=3), "The test must release its embedding worker"
        return embedding_response([[1.0] * 384])

    backend = FreellmpoolEmbedding(
        "verified-embedding-model", provider_config=embedding_catalog,
        processing_policy=approved_embedding_policy,
        transport=httpx.MockTransport(respond), timeout_s=0.04,
    )
    running = asyncio.create_task(backend.embed(["Complete source"] ))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(running, timeout=1)
        with pytest.raises(TimeoutError):
            await backend.embed(["Expired while waiting for worker"])
        assert len(calls) == 1
    finally:
        release.set()
        await asyncio.gather(running, return_exceptions=True)
        await backend.aclose()


async def test_cancelling_close_does_not_abandon_its_embedding_worker(
    embedding_catalog: Path, approved_embedding_policy: RemoteProcessingPolicy,
) -> None:
    entered = asyncio.Event()
    release = threading.Event()
    closed = threading.Event()
    loop = asyncio.get_running_loop()

    class ObservedTransport(httpx.MockTransport):
        def close(self) -> None:
            closed.set()
            super().close()

    def respond(request: httpx.Request) -> httpx.Response:
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(timeout=3)
        return embedding_response([[1.0] * 384])

    backend = FreellmpoolEmbedding(
        "verified-embedding-model", provider_config=embedding_catalog, transport=ObservedTransport(respond),
        processing_policy=approved_embedding_policy,
    )
    running = asyncio.create_task(backend.embed(["Complete source"]))
    closing = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        closing = asyncio.create_task(backend.aclose())
        await asyncio.sleep(0)
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
        assert not closed.is_set()
        release.set()
        await running
        await backend.aclose()
        assert closed.is_set()
    finally:
        release.set()
        await asyncio.gather(running, *([closing] if closing is not None else []), return_exceptions=True)
        await backend.aclose()


@pytest.mark.parametrize("context", [None, LLMRequestContext(owner_user_id="owner-a", data_classification="private")])
async def test_embedding_catalog_cannot_authorize_missing_context_or_private_processing(
    embedding_catalog: Path, context: LLMRequestContext | None, approved_embedding_policy: RemoteProcessingPolicy,
) -> None:
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return embedding_response([[1.0] * 384])

    backend = FreellmpoolEmbedding(
        "verified-embedding-model", provider_config=embedding_catalog, transport=httpx.MockTransport(respond),
        processing_policy=approved_embedding_policy,
    )
    try:
        with pytest.raises(ValueError, match="(?i)(processing|context|approved)"):
            if context is None:
                await Context().run(asyncio.create_task, backend.embed(["Unclassified private evidence"]))
            else:
                with llm_request_context(context):
                    await backend.embed(["Private evidence"])
        assert calls == []
    finally:
        await backend.aclose()


async def test_private_embedding_requires_independent_server_policy_for_the_exact_destination(embedding_catalog: Path) -> None:
    policy = RemoteProcessingPolicy(
        policy_id="reviewed-private-embedding", private_providers=frozenset({"freellmpool", "approved-remote"}),
    )
    backend = FreellmpoolEmbedding(
        "verified-embedding-model", provider_config=embedding_catalog, processing_policy=policy,
        transport=httpx.MockTransport(lambda request: embedding_response([[1.0] + [0.0] * 383])),
    )
    try:
        with llm_request_context(LLMRequestContext(owner_user_id="owner-a", data_classification="private")):
            assert await backend.embed(["Complete approved private evidence"]) == [[1.0] + [0.0] * 383]
    finally:
        await backend.aclose()


def test_embedding_factory_forwards_the_server_processing_policy(embedding_catalog: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}
    policy = RemoteProcessingPolicy(policy_id="reviewed-policy")

    def construct(**options):
        captured.update(options)
        return SimpleNamespace()

    monkeypatch.setattr("bebshax.llm.adapters.factory.FreellmpoolEmbedding", construct)
    build_embedding_backend(
        "freellmpool", "verified-embedding-model", provider_config=embedding_catalog, processing_policy=policy,
    )
    assert captured["provider_config"] == embedding_catalog
    assert captured["processing_policy"] is policy


@pytest.mark.parametrize("valid_response", [False, True])
async def test_embedding_daily_quota_counts_attempts_once_including_rejected_vectors(
    embedding_catalog: Path, valid_response: bool, approved_embedding_policy: RemoteProcessingPolicy,
) -> None:
    allowance = 2 if valid_response else 1
    embedding_catalog.write_text(
        embedding_catalog.read_text(encoding="utf-8") + f"rpd={allowance}\n", encoding="utf-8",
    )
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return embedding_response([[1.0] * (384 if valid_response else 12)])

    backend = FreellmpoolEmbedding(
        "verified-embedding-model", provider_config=embedding_catalog, transport=httpx.MockTransport(respond),
        processing_policy=approved_embedding_policy,
    )
    try:
        if valid_response:
            for _attempt in range(allowance):
                assert len((await backend.embed(["Complete evidence"]))[0]) == 384
        else:
            with pytest.raises(ValueError, match="dimension"):
                await backend.embed(["Complete evidence"])
        with pytest.raises((ValueError, AllProvidersExhausted), match="(?i)(quota|allowance)"):
            await backend.embed(["Another full source"])
        assert len(calls) == allowance
    finally:
        await backend.aclose()


async def test_embedding_retry_after_date_blocks_early_followup_http(
    embedding_catalog: Path, approved_embedding_policy: RemoteProcessingPolicy,
) -> None:
    calls = []
    recovery = format_datetime(datetime.now(timezone.utc) + timedelta(hours=1), usegmt=True)

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": recovery}, json={"error": {"message": "synthetic account limit"}})

    backend = FreellmpoolEmbedding(
        "verified-embedding-model", provider_config=embedding_catalog, transport=httpx.MockTransport(respond),
        processing_policy=approved_embedding_policy,
    )
    try:
        with pytest.raises(AllProvidersExhausted):
            await backend.embed(["Complete evidence"])
        with pytest.raises((ValueError, AllProvidersExhausted), match="(?i)(cooling|recovery)"):
            await backend.embed(["Another full source"])
        assert len(calls) == 1
    finally:
        await backend.aclose()
