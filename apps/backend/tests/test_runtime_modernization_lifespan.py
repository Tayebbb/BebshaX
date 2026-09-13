import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI

from bebshax import main
from bebshax.api import jobs as job_api
from bebshax.config import Settings
from bebshax.db import capacity_state
from bebshax.db.engine import SchemaValidationError
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.provenance import ProvenanceRecord
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType


def _setup(monkeypatch, **overrides):
    events = []
    settings = Settings(_env_file=None, **overrides)
    engine = SimpleNamespace(dispose=AsyncMock(side_effect=lambda: events.append("engine-close")))
    maker = object()
    sink = SimpleNamespace(
        start=AsyncMock(side_effect=lambda: events.append("sink-start")),
        stop=AsyncMock(side_effect=lambda: events.append("sink-close")), persist=AsyncMock(),
    )

    class Store:
        async def load_active(self):
            events.append("cooldowns")
            return {("cerebras", "*"): 999999999.0}

        def persist(self, *args):
            pass

        async def aclose(self):
            events.append("cooldown-close")

    class Adapter(FakeAdapter):
        async def aclose(self):
            events.append("adapter-close")

        async def candidates(self):
            events.append("candidates")
            return await super().candidates()

        async def seed_metrics(self, observations):
            events.append("metrics")
            return len(observations)

    class Persona:
        def __init__(self, path, *, expected_manifest=None):
            self.artifact_dir = path
            self.expected_manifest = expected_manifest

        async def readiness(self):
            return {"status": "available", "reason": None}

        async def aclose(self):
            events.append("ml-close")

    adapters = {
        "freellmpool": Adapter([FakeRoute(RouteCandidate(provider="groq", model="test", context_window=10000))]),
        "openrouter": Adapter([]),
    }

    async def initialize(*args, **kwargs):
        events.append("database")

    async def provenance(*args):
        events.append("provenance")
        return [ProvenanceRecord(request_id="seed", task="PERSONA_RESPONSE", served_by_provider="groq", success=True)]

    async def observations(*args):
        events.append("observations")
        return [("groq", "test", 25.0)]

    build = MagicMock(side_effect=lambda **kwargs: events.append("adapters") or adapters)
    initialize_jobs = AsyncMock(side_effect=lambda app: events.append("jobs-start"))
    monkeypatch.setattr(job_api, "initialize_jobs", initialize_jobs)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "create_engine", lambda settings: engine)
    monkeypatch.setattr(main, "create_async_sessionmaker", lambda engine: maker)
    monkeypatch.setattr(main, "init_database", initialize)
    monkeypatch.setattr(main, "ProvenanceSink", lambda maker: sink)
    monkeypatch.setattr(main, "build_default_adapters", build)
    monkeypatch.setattr(main, "MLPersonaAdapter", Persona)
    monkeypatch.setattr(capacity_state, "CooldownStore", lambda maker: Store())
    monkeypatch.setattr(capacity_state, "load_todays_provenance", provenance)
    monkeypatch.setattr(capacity_state, "load_todays_consumption", AsyncMock(return_value=({}, {})))
    monkeypatch.setattr(capacity_state, "load_recent_route_observations", observations)
    return SimpleNamespace(events=events, settings=settings, engine=engine, maker=maker,
                           sink=sink, build=build, adapters=adapters, initialize_jobs=initialize_jobs)


async def test_job_recovery_starts_before_application_readiness(monkeypatch):
    runtime = _setup(monkeypatch)
    app = FastAPI()

    async def initialize_jobs(application):
        assert application is app
        assert application.state.core_ready is False
        assert application.state.db_sessionmaker is runtime.maker
        assert application.state.llm_service is application.state.llm_router
        runtime.events.append("jobs-start")

    runtime.initialize_jobs.side_effect = initialize_jobs
    async with main._lifespan(app):
        runtime.initialize_jobs.assert_awaited_once_with(app)
        assert "jobs-start" in runtime.events
        assert app.state.core_ready is True


async def test_job_recovery_failure_prevents_readiness_and_closes_resources(monkeypatch):
    runtime = _setup(monkeypatch)
    runtime.initialize_jobs.side_effect = RuntimeError("job recovery failed")
    app = FastAPI()
    with pytest.raises(RuntimeError, match="job recovery failed"):
        async with main._lifespan(app):
            pytest.fail("Job recovery failure must prevent readiness")
    assert app.state.core_ready is False
    runtime.sink.stop.assert_awaited_once()
    runtime.engine.dispose.assert_awaited_once()


async def test_database_is_validated_before_restores_and_factory(monkeypatch):
    runtime = _setup(monkeypatch)
    app = FastAPI()
    async with main._lifespan(app):
        assert runtime.events[0] == "database"
        assert runtime.events.index("provenance") < runtime.events.index("adapters")
        assert runtime.events.index("cooldowns") < runtime.events.index("adapters")
        assert "candidates" not in runtime.events
        assert app.state.core_ready is True
        assert app.state.llm_service is app.state.llm_router
        assert app.state.quota_ledger.used_today("groq") == (1, 0)
        options = runtime.build.call_args.kwargs
        assert options["quota_ledger"] is app.state.quota_ledger
        assert options["provider_config"] == runtime.settings.provider_config_path
        assert options["initial_cooldowns"] == {("cerebras", "*"): 999999999.0}
        assert callable(options["on_cooldown_change"])
        assert not hasattr(app.state, "local_tier_up")
    assert app.state.core_ready is False
    assert runtime.events[-1] == "engine-close"


async def test_database_failure_stops_consumers_and_disposes_engine(monkeypatch, caplog):
    runtime = _setup(monkeypatch)
    monkeypatch.setattr(main, "init_database", AsyncMock(side_effect=RuntimeError("private-database-detail")))
    with pytest.raises(RuntimeError):
        async with main._lifespan(FastAPI()):
            pytest.fail("Startup must not yield after failed database validation")
    runtime.engine.dispose.assert_awaited_once()
    runtime.build.assert_not_called()
    runtime.sink.start.assert_not_awaited()
    assert "private-database-detail" not in caplog.text


@pytest.mark.parametrize(
    ("failure", "logged", "withheld"),
    [
        (SchemaValidationError("Database schema is not at the Alembic head."), "not at the Alembic head", None),
        (OSError("connect to db-host.internal:5432 failed"), "OSError", "db-host.internal"),
    ],
)
async def test_database_failure_log_names_schema_state_or_only_the_error_class(
    monkeypatch, caplog, failure, logged, withheld,
):
    runtime = _setup(monkeypatch)
    monkeypatch.setattr(main, "init_database", AsyncMock(side_effect=failure))
    with caplog.at_level(logging.ERROR, logger="bebshax.main"), pytest.raises(RuntimeError):
        async with main._lifespan(FastAPI()):
            pytest.fail("Startup must not yield after failed database validation")
    assert f"Database startup validation failed: " in caplog.text
    assert logged in caplog.text
    if withheld is not None:
        assert withheld not in caplog.text
    runtime.engine.dispose.assert_awaited_once()


async def test_partial_startup_failure_closes_every_acquired_resource(monkeypatch):
    runtime = _setup(monkeypatch)
    monkeypatch.setattr(main, "MemoryService", MagicMock(side_effect=RuntimeError("assembly failed")))
    with pytest.raises(RuntimeError):
        async with main._lifespan(FastAPI()):
            pytest.fail("Broken assembly must not yield")
    runtime.sink.stop.assert_awaited_once()
    assert runtime.events.count("adapter-close") == 2
    assert "ml-close" in runtime.events
    assert runtime.events[-1] == "engine-close"


async def test_child_tasks_are_cancelled_before_dependencies_close(monkeypatch):
    runtime = _setup(monkeypatch)
    started = asyncio.Event()

    async def child():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            runtime.events.append("child-close")

    app = FastAPI()
    with pytest.raises(ValueError, match="body failed"):
        async with main._lifespan(app):
            task = app.state.register_runtime_task(asyncio.create_task(child()))
            await started.wait()
            raise ValueError("body failed")
    assert task.cancelled()
    assert runtime.events.index("child-close") < runtime.events.index("ml-close")
    assert runtime.events.index("ml-close") < runtime.events.index("engine-close")


async def test_lifespan_defers_dependency_cleanup_until_cancel_resistant_child_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _setup(monkeypatch, runtime_shutdown_timeout_s=0.02)
    started = asyncio.Event()
    cancelled = asyncio.Event()
    release = asyncio.Event()
    app = FastAPI()
    child_task = None

    async def child():
        started.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.set()
        runtime.events.append("child-close")

    try:
        with pytest.raises(RuntimeError, match="did not stop"):
            async with asyncio.timeout(2), main._lifespan(app):
                child_task = app.state.register_runtime_task(asyncio.create_task(child()))
                await asyncio.wait_for(started.wait(), timeout=1)
        assert cancelled.is_set()
        assert not child_task.done()
        assert app.state.core_ready is False
        assert not any(event.endswith("-close") for event in runtime.events)
        assert app.state.runtime_shutdown_status == "degraded"
        assert not app.state.runtime_cleanup_task.done()
    finally:
        release.set()
        if child_task is not None:
            await asyncio.wait_for(asyncio.gather(child_task, return_exceptions=True), timeout=1)
        cleanup = getattr(app.state, "runtime_cleanup_task", None)
        if cleanup is not None:
            await asyncio.wait_for(asyncio.shield(cleanup), timeout=1)

    assert runtime.events.index("child-close") < runtime.events.index("ml-close")
    assert runtime.events.index("child-close") < runtime.events.index("sink-close")
    assert runtime.events.count("adapter-close") == 2
    runtime.sink.stop.assert_awaited_once()
    runtime.engine.dispose.assert_awaited_once()


async def test_lifespan_stops_job_admission_and_recovery_before_registry_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    initialize_jobs = job_api.initialize_jobs
    runtime = _setup(monkeypatch)
    runtime.initialize_jobs.side_effect = initialize_jobs
    app = FastAPI()
    store = MagicMock(spec=job_api.MemoryJobStore)
    store.recover = AsyncMock(return_value=[])
    store.interrupt_worker = AsyncMock()
    store.admit = AsyncMock(return_value=SimpleNamespace(created=True, job={"job_id": "shutdown-race"}))
    app.state.job_store = store
    started = asyncio.Event()
    release = asyncio.Event()
    observed = {}
    child_task = None

    async def child():
        started.set()
        try:
            await release.wait()
        finally:
            observed["recovery_stopped"] = app.state.job_runtime._recovery_task.done()
            try:
                await job_api.prepare_job(
                    app, kind="research", scope_id="study-test", user_id="owner-test", input_data={},
                )
            except job_api.APIError as exc:
                observed["admission"] = exc.error_code
            else:
                observed["admission"] = "accepted"

    try:
        async with main._lifespan(app):
            child_task = app.state.register_runtime_task(asyncio.create_task(child()))
            await asyncio.wait_for(started.wait(), timeout=1)
        assert observed == {"recovery_stopped": True, "admission": "job_runtime_closing"}
        assert child_task.cancelled()
        store.admit.assert_not_awaited()
        runtime.sink.stop.assert_awaited_once()
        runtime.engine.dispose.assert_awaited_once()
    finally:
        release.set()
        if child_task is not None:
            await asyncio.wait_for(asyncio.gather(child_task, return_exceptions=True), timeout=1)


async def test_lifespan_retains_dependencies_through_job_worker_finalization(monkeypatch: pytest.MonkeyPatch) -> None:
    initialize_jobs = job_api.initialize_jobs
    runtime = _setup(monkeypatch, runtime_shutdown_timeout_s=0.02)
    runtime.initialize_jobs.side_effect = initialize_jobs
    app = FastAPI()
    store = job_api.MemoryJobStore()
    app.state.job_store = store
    started = asyncio.Event()
    release = asyncio.Event()
    interrupt_worker = store.interrupt_worker
    worker_task = None

    async def interrupt(worker_id, *, job_id=None):
        if job_id is not None:
            assert not any(event.endswith("-close") for event in runtime.events)
            runtime.events.append("job-finalized")
        return await interrupt_worker(worker_id, job_id=job_id)

    async def runner(job):
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()

    monkeypatch.setattr(store, "interrupt_worker", interrupt)
    try:
        with pytest.raises(RuntimeError, match="did not stop"):
            async with asyncio.timeout(2), main._lifespan(app):
                accepted = await job_api.start_job_async(
                    app, kind="research", scope_id="study-test", user_id="owner-test",
                    input_data={}, runner=runner,
                )
                worker_task = next(iter(app.state.job_runtime.tasks))
                await asyncio.wait_for(started.wait(), timeout=1)
        assert not worker_task.done()
        assert worker_task.cancelling() == 1
        assert app.state.job_runtime._recovery_task.done()
        assert not any(event.endswith("-close") for event in runtime.events)
        saved = await job_api.get_job_async(
            app, accepted["job_id"], kind="research", scope_id="study-test", user_id="owner-test",
        )
        assert saved["state"] == "interrupted"
        with pytest.raises(job_api.APIError) as rejected:
            await job_api.prepare_job(
                app, kind="research", scope_id="study-test", user_id="owner-test", input_data={},
            )
        assert rejected.value.error_code == "job_runtime_closing"
    finally:
        release.set()
        if worker_task is not None:
            await asyncio.wait_for(asyncio.gather(worker_task, return_exceptions=True), timeout=1)
        cleanup = getattr(app.state, "runtime_cleanup_task", None)
        if cleanup is not None:
            await asyncio.wait_for(asyncio.shield(cleanup), timeout=1)
    assert runtime.events.index("job-finalized") < runtime.events.index("sink-close")
    runtime.sink.stop.assert_awaited_once()
    runtime.engine.dispose.assert_awaited_once()


async def test_cancelled_lifespan_retains_dependencies_until_children_drain(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _setup(monkeypatch, runtime_shutdown_timeout_s=1)
    app = FastAPI()
    started = asyncio.Event()
    cancelled = asyncio.Event()
    release = asyncio.Event()

    async def child():
        started.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.set()
        runtime.events.append("child-close")

    lifespan = main._lifespan(app)
    await lifespan.__aenter__()
    child_task = app.state.register_runtime_task(asyncio.create_task(child()))
    shutdown = None
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        shutdown = asyncio.create_task(lifespan.__aexit__(None, None, None))
        await asyncio.wait_for(cancelled.wait(), timeout=1)
        shutdown.cancel()
        with pytest.raises(asyncio.CancelledError):
            await shutdown
        assert not child_task.done()
        assert app.state.core_ready is False
        assert app.state.runtime_shutdown_status == "degraded"
        assert not any(event.endswith("-close") for event in runtime.events)
    finally:
        release.set()
        await asyncio.wait_for(asyncio.gather(child_task, return_exceptions=True), timeout=1)
        if shutdown is None:
            await lifespan.__aexit__(None, None, None)
        else:
            await asyncio.wait_for(asyncio.gather(shutdown, return_exceptions=True), timeout=2)
        cleanup = getattr(app.state, "runtime_cleanup_task", None)
        if cleanup is not None:
            await asyncio.wait_for(asyncio.shield(cleanup), timeout=1)
    assert runtime.events.index("child-close") < runtime.events.index("sink-close")
    runtime.engine.dispose.assert_awaited_once()


async def test_deferred_cleanup_failure_is_observable_after_children_drain(monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    runtime = _setup(monkeypatch, runtime_shutdown_timeout_s=0.02)
    app = FastAPI()
    started = asyncio.Event()
    release = asyncio.Event()
    resource = SimpleNamespace(aclose=AsyncMock(side_effect=ValueError("private-close-detail")))
    child_task = None

    async def child():
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()
        runtime.events.append("child-close")

    try:
        with pytest.raises(RuntimeError, match="did not stop"):
            async with main._lifespan(app):
                app.state.register_runtime_resource(resource)
                child_task = app.state.register_runtime_task(asyncio.create_task(child()))
                await asyncio.wait_for(started.wait(), timeout=1)
        resource.aclose.assert_not_awaited()
        release.set()
        with pytest.raises(ValueError, match="private-close-detail"):
            await asyncio.wait_for(asyncio.shield(app.state.runtime_cleanup_task), timeout=1)
        assert app.state.runtime_shutdown_status == "cleanup_failed"
        assert "Deferred runtime resource cleanup failed" in caplog.text
        assert "private-close-detail" not in caplog.text
        resource.aclose.assert_awaited_once()
        runtime.sink.stop.assert_awaited_once()
        runtime.engine.dispose.assert_awaited_once()
    finally:
        release.set()
        if child_task is not None:
            await asyncio.wait_for(asyncio.gather(child_task, return_exceptions=True), timeout=1)
        cleanup = getattr(app.state, "runtime_cleanup_task", None)
        if cleanup is not None:
            await asyncio.wait_for(asyncio.gather(cleanup, return_exceptions=True), timeout=1)


@pytest.mark.parametrize("during_shutdown", [False, True])
async def test_registry_keeps_rejected_running_tasks_owned_until_they_stop(during_shutdown: bool) -> None:
    registry = main.RuntimeTaskRegistry(timeout_s=0.02)
    started = asyncio.Event()
    release = asyncio.Event()
    rejected = asyncio.Event()
    owner_started = asyncio.Event()
    owner_task = None

    async def child():
        started.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                pass

    child_task = asyncio.create_task(child())

    def register_rejected():
        with pytest.raises(RuntimeError, match="registry is closed"):
            registry.register(child_task)
        rejected.set()

    async def owner():
        owner_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            register_rejected()

    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        if during_shutdown:
            owner_task = registry.register(asyncio.create_task(owner()))
            await asyncio.wait_for(owner_started.wait(), timeout=1)
        else:
            await registry.aclose()
            register_rejected()
        with pytest.raises(RuntimeError, match="did not stop"):
            await registry.aclose()
        assert rejected.is_set()
        assert not child_task.done()
    finally:
        release.set()
        if owner_task is not None:
            owner_task.cancel()
            await asyncio.wait_for(asyncio.gather(owner_task, return_exceptions=True), timeout=1)
        await asyncio.wait_for(asyncio.gather(child_task, return_exceptions=True), timeout=1)
        await asyncio.wait_for(registry.drain(), timeout=1)


async def test_routed_provenance_is_awaited_and_accounted(monkeypatch):
    runtime = _setup(monkeypatch)
    app = FastAPI()
    async with main._lifespan(app):
        result = await app.state.llm_service.complete(LLMRequest(
            task=TaskType.PERSONA_RESPONSE, messages=[ChatMessage(role="user", content="hello")],
        ))
        runtime.sink.persist.assert_awaited_once_with(result.provenance)
        assert result.provenance.persistence_status == "acknowledged"
        assert app.state.quota_ledger.used_today("groq")[0] == 2


async def test_manifest_is_passed_only_to_a_supported_constructor(monkeypatch):
    _setup(monkeypatch, ml_persona_manifest_sha256="a" * 64)
    app = FastAPI()
    async with main._lifespan(app):
        assert app.state.persona_ml.expected_manifest.metadata_sha256 == "a" * 64


async def test_explicit_processing_policy_is_shared_by_router_and_embeddings(monkeypatch):
    from bebshax.llm.adapters.embeddings import HashEmbedding
    from bebshax.llm.governance import RemoteProcessingPolicy

    policy = RemoteProcessingPolicy(
        policy_id="test-approved-synthetic",
        synthetic_providers=frozenset({"freellmpool", "groq", "openrouter"}),
        synthetic_openrouter_upstreams=frozenset({"test-upstream"}),
    )
    runtime = _setup(
        monkeypatch, remote_processing_policy=policy,
        embedding_backend="freellmpool", embedding_model="test-embedding",
    )
    router_factory = MagicMock(wraps=main.PoolRouter)
    embedding_options = {}

    def embedding_factory(backend, model, *, provider_config=None, processing_policy=None):
        embedding_options.update(provider_config=provider_config, processing_policy=processing_policy)
        return HashEmbedding()

    monkeypatch.setattr(main, "PoolRouter", router_factory)
    monkeypatch.setattr(main, "build_embedding_backend", embedding_factory)
    async with main._lifespan(FastAPI()):
        assert router_factory.call_args.kwargs.get("processing_policy") == policy
        assert embedding_options["processing_policy"] == policy
        assert embedding_options["provider_config"] == runtime.settings.provider_config_path


async def test_legacy_ml_constructor_does_not_receive_unsupported_keywords(monkeypatch):
    _setup(monkeypatch)
    legacy = MagicMock()
    legacy.artifact_dir = Path("missing-runtime-artifact")
    monkeypatch.setattr(main, "MLPersonaAdapter", lambda path: legacy)
    app = FastAPI()
    async with main._lifespan(app):
        assert app.state.persona_ml is legacy
        assert app.state.core_ready is True


async def test_required_missing_ml_capability_is_an_explicit_gate(monkeypatch):
    runtime = _setup(monkeypatch, ml_persona_required=True)

    class MissingPersona:
        def __init__(self, path):
            pass

        async def readiness(self):
            return {"status": "unavailable", "reason": "artifact_unavailable"}

    monkeypatch.setattr(main, "MLPersonaAdapter", MissingPersona)
    with pytest.raises(RuntimeError):
        async with main._lifespan(FastAPI()):
            pytest.fail("Required unavailable ML capability must fail startup")
    runtime.engine.dispose.assert_awaited_once()


async def test_migration_guard_resolves_config_location_and_disposes_on_failure(monkeypatch, tmp_path):
    ini = tmp_path / "alembic.ini"
    ini.write_text("[alembic]\nscript_location = migrations\n", encoding="utf-8")
    engine = MagicMock()
    engine.connect.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("connect failed"))
    engine.dispose = AsyncMock()
    factory = MagicMock(return_value=engine)
    scripts = MagicMock()
    scripts.get_heads.return_value = ["expected-head"]
    script_factory = MagicMock(return_value=scripts)
    monkeypatch.setattr(main, "create_async_engine", factory)
    monkeypatch.setattr(main.ScriptDirectory, "from_config", script_factory)
    with pytest.raises(RuntimeError):
        await main.check_migrations_current_async("sqlite+aiosqlite:///:memory:", str(ini))
    engine.dispose.assert_awaited_once()
    assert factory.call_args.kwargs["hide_parameters"] is True
    config = script_factory.call_args.args[0]
    assert Path(config.get_main_option("script_location")) == tmp_path / "migrations"


@pytest.mark.parametrize("heads", [[], ["head-one", "head-two"]])
async def test_migration_guard_rejects_empty_or_multiple_source_heads(monkeypatch, heads):
    scripts = MagicMock()
    scripts.get_heads.return_value = heads
    monkeypatch.setattr(main.ScriptDirectory, "from_config", lambda config: scripts)
    factory = MagicMock()
    monkeypatch.setattr(main, "create_async_engine", factory)
    with pytest.raises(RuntimeError):
        await main.check_migrations_current_async("sqlite+aiosqlite:///:memory:")
    factory.assert_not_called()


async def test_ml_manifest_readiness_is_lazy_and_requires_trusted_digest(ml_artifact):
    import hashlib

    from bebshax_persona_ml.provenance import ExpectedArtifactManifest

    adapter = SimpleNamespace(artifact_dir=ml_artifact)
    expected = ExpectedArtifactManifest(metadata_sha256=hashlib.sha256((ml_artifact / "metadata.json").read_bytes()).hexdigest())
    capability = await main._persona_capability(adapter, expected)
    assert capability["status"] == "configured"
    assert capability["validation"] == "manifest"
    assert capability["model_loaded"] is False
    wrong = ExpectedArtifactManifest(metadata_sha256="0" * 64)
    assert (await main._persona_capability(adapter, wrong))["status"] == "unavailable"


async def test_invalid_manifest_is_unavailable_without_loading_model(tmp_path):
    artifact = tmp_path / "invalid-model"
    artifact.mkdir()
    (artifact / "metadata.json").write_text("{}", encoding="utf-8")
    adapter = SimpleNamespace(artifact_dir=artifact)
    assert (await main._persona_capability(adapter))["status"] == "unavailable"


async def test_required_valid_lazy_manifest_keeps_application_ready(monkeypatch, ml_artifact):
    _setup(monkeypatch, ml_persona_required=True, ml_persona_artifact_dir=str(ml_artifact))
    monkeypatch.setattr(main, "MLPersonaAdapter", lambda path: SimpleNamespace(artifact_dir=path))
    app = FastAPI()
    async with main._lifespan(app):
        assert app.state.core_ready is True
        assert app.state.persona_capability["status"] == "configured"


async def test_hosted_ml_without_manifest_pin_is_explicitly_unavailable(monkeypatch):
    _setup(monkeypatch, environment="production", resend_api_key="test-mail-provider",
           email_from_address="test@example.com")
    app = FastAPI()
    async with main._lifespan(app):
        assert app.state.core_ready is True
        assert app.state.persona_capability == {"status": "unavailable", "reason": "expected_manifest_required"}


async def test_accounting_failure_still_awaits_durable_provenance(monkeypatch):
    from bebshax.llm.failures import LLMError

    runtime = _setup(monkeypatch)
    app = FastAPI()
    async with main._lifespan(app):
        monkeypatch.setattr(app.state.quota_ledger, "record", MagicMock(side_effect=RuntimeError("accounting failed")))
        with pytest.raises(LLMError):
            await app.state.llm_service.complete(LLMRequest(
                task=TaskType.PERSONA_RESPONSE, messages=[ChatMessage(role="user", content="hello")],
            ))
        runtime.sink.persist.assert_awaited_once()


async def test_remote_embeddings_fail_closed_without_explicit_catalog_factory(monkeypatch):
    runtime = _setup(monkeypatch, embedding_backend="freellmpool", embedding_model="approved-model")
    monkeypatch.setattr(main, "build_embedding_backend", lambda backend, model: object())
    app = FastAPI()
    with pytest.raises(RuntimeError, match="explicit provider configuration"):
        async with main._lifespan(app):
            pytest.fail("Remote embeddings must not load an implicit provider configuration")
    runtime.engine.dispose.assert_awaited_once()


async def test_remote_embeddings_receive_explicit_configuration_when_supported(monkeypatch):
    from bebshax.llm.adapters.embeddings import HashEmbedding

    runtime = _setup(monkeypatch, embedding_backend="freellmpool", embedding_model="approved-model")
    calls = []

    def embedding_factory(backend, model, *, provider_config, processing_policy):
        calls.append((backend, model, provider_config, processing_policy))
        return HashEmbedding()

    monkeypatch.setattr(main, "build_embedding_backend", embedding_factory)
    app = FastAPI()
    async with main._lifespan(app):
        # Embeddings and the router must share one effective policy object.
        assert calls == [(
            "freellmpool", "approved-model", runtime.settings.provider_config_path,
            app.state.remote_processing_policy,
        )]
        assert app.state.llm_router._processing_policy is app.state.remote_processing_policy


async def test_unset_remote_processing_policy_approves_the_configured_catalog(monkeypatch, caplog):
    runtime = _setup(monkeypatch)
    assert "remote_processing_policy" not in runtime.settings.model_fields_set
    app = FastAPI()
    with caplog.at_level(logging.INFO, logger="bebshax.main"):
        async with main._lifespan(app):
            policy = app.state.remote_processing_policy
            assert policy.policy_id == "configured-providers-default"
            assert {"freellmpool", "openrouter", "pollinations", "ovh", "kilo"} <= set(policy.private_providers)
            assert policy.private_providers == policy.synthetic_providers
            assert policy.private_openrouter_upstreams == frozenset({"*"})
    assert any("BEBSHAX_REMOTE_PROCESSING_POLICY is not set" in record.getMessage() for record in caplog.records)


async def test_explicit_remote_processing_policy_is_used_verbatim(monkeypatch):
    from bebshax.llm.governance import RemoteProcessingPolicy

    explicit = RemoteProcessingPolicy(policy_id="reviewed-private-v9", private_providers=frozenset({"freellmpool"}))
    _setup(monkeypatch, remote_processing_policy=explicit)
    app = FastAPI()
    async with main._lifespan(app):
        assert app.state.remote_processing_policy is explicit
        assert app.state.llm_router._processing_policy is explicit


def test_missing_policy_in_hosted_environments_is_a_warning(monkeypatch, caplog):
    settings = Settings(
        _env_file=None, environment="production", jwt_secret="x" * 48, resend_api_key="re_fixture_key",
        email_from_address="ops@example.test", database_url="postgresql+asyncpg://user:pw@db.example.test/bebshax",
    )
    with caplog.at_level(logging.WARNING, logger="bebshax.main"):
        policy = main.effective_processing_policy(settings)
    assert policy.policy_id == "configured-providers-default"
    assert any(record.levelno == logging.WARNING and "not set" in record.getMessage() for record in caplog.records)