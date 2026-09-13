"""FastAPI application entry point: `uvicorn bebshax.main:app`."""

import asyncio
import hashlib
import inspect
import json
import logging
import re
from collections.abc import Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:
    from bebshax_persona_ml.provenance import ExpectedArtifactManifest

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware
from bebshax.api.errors import (
    APIError,
    REQUEST_ID_HEADER,
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
    UnhandledExceptionEnvelopeMiddleware,
    register_exception_handlers,
)
from bebshax.api.limiter import limiter

from bebshax import __version__
from bebshax.api import jobs as job_api
from bebshax.api.auth import auth_router
from bebshax.api.copilot import router as copilot_router
from bebshax.api.evaluation import router as evaluation_router
from bebshax.api.health import provider_status_snapshot, record_provider_observations, router as health_router
from bebshax.api.interviews import router as interviews_router
from bebshax.api.personas import router as personas_router
from bebshax.api.routes import router as routes_router
from bebshax.api.studies import router as studies_router
from bebshax.config import Settings, export_provider_credentials, fail_fast_on_invalid_settings, get_settings
from bebshax.db.engine import SchemaValidationError, create_async_sessionmaker, create_engine, init_database
from bebshax.db.models import Base, Businesses, LLMRequests, ModelRegistry, Personas, SavedAudiences, Studies  # noqa: F401
from bebshax.db.sink import ProvenanceSink
from bebshax.interview.engine import InterviewEngine
from bebshax.interview.orm import Conversations, ConversationTurns  # noqa: F401
from bebshax.llm.adapters.factory import (
    build_default_adapters,
    build_embedding_backend,
    default_processing_policy,
)
from bebshax.llm.governance import RemoteProcessingPolicy
from bebshax.llm.router import PoolRouter
from bebshax.llm.provenance import ProvenanceRecord
from bebshax.memory.service import MemoryService
from bebshax.persona.evidence import EvidenceStore
from bebshax.persona.generation import PersonaEngine
from bebshax.persona.orm import PersonaAttributes, PersonaDetails, PersonaEvidence  # noqa: F401
from bebshax.personas.ml_adapter import MLPersonaAdapter

logger = logging.getLogger(__name__)


def effective_processing_policy(settings: Settings) -> RemoteProcessingPolicy:
    """Explicit BEBSHAX_REMOTE_PROCESSING_POLICY wins; otherwise approve the
    reviewed provider catalog instead of silently denying every AI call."""
    if "remote_processing_policy" in settings.model_fields_set:
        return settings.remote_processing_policy
    policy = default_processing_policy(settings.provider_config_path)
    level = logging.WARNING if settings.environment in ("production", "staging") else logging.INFO
    logger.log(
        level, "BEBSHAX_REMOTE_PROCESSING_POLICY is not set; using policy %s approving providers %s",
        policy.policy_id, sorted(policy.private_providers),
    )
    return policy


class RuntimeTaskRegistry:
    """Public application hook for child-task ownership without feature imports."""

    def __init__(self, timeout_s: float) -> None:
        self._timeout_s = timeout_s
        self._tasks: set[asyncio.Task] = set()
        self._closed = False

    def register(self, task: asyncio.Task) -> asyncio.Task:
        self._tasks.add(task)
        task.add_done_callback(self._finished)
        if self._closed:
            if not task.cancelling():
                task.cancel()
            raise RuntimeError("Runtime task registry is closed")
        return task

    def _finished(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Runtime child task failed")

    async def aclose(self) -> None:
        self._closed = True
        tasks = tuple(self._tasks)
        for task in tasks:
            if not task.cancelling():
                task.cancel()
        try:
            async with asyncio.timeout(self._timeout_s):
                await self.drain()
        except TimeoutError:
            raise RuntimeError("Runtime child tasks did not stop before shutdown") from None

    async def drain(self) -> None:
        while self._tasks:
            await asyncio.wait(tuple(self._tasks))


async def _close_resource(resource: Any, timeout_s: float) -> None:
    close = getattr(resource, "aclose", None) or getattr(resource, "close", None)
    if callable(close):
        async with asyncio.timeout(timeout_s):
            result = close()
            if inspect.isawaitable(result):
                await result


class _UnavailablePersonaModel:
    def __init__(self, artifact_dir: Path, reason: str) -> None:
        self.artifact_dir = artifact_dir
        self.reason = reason

    async def readiness(self) -> dict[str, Any]:
        return {"status": "unavailable", "reason": self.reason}

    async def generate(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise APIError(503, "Persona generation is unavailable.", error_code="ml_persona_unavailable")


def _build_persona_model(settings: Settings) -> Any:
    path = settings.ml_persona_artifact_path
    expected = settings.expected_ml_persona_manifest
    if not settings.ml_persona_enabled:
        return _UnavailablePersonaModel(path, "feature_disabled")
    if settings.environment in ("production", "staging") and expected is None:
        return _UnavailablePersonaModel(path, "expected_manifest_required")
    parameters = inspect.signature(MLPersonaAdapter).parameters
    if expected is not None:
        if "expected_manifest" not in parameters:
            return _UnavailablePersonaModel(path, "adapter_manifest_unsupported")
        return MLPersonaAdapter(path, expected_manifest=expected)
    return MLPersonaAdapter(path)


def _manifest_capability(path: Path, expected: "ExpectedArtifactManifest | None") -> dict[str, Any]:
    from bebshax_persona_ml.model import ALGORITHMS, FILE_LIMITS, RUNTIME

    unavailable = {"status": "unavailable", "reason": "artifact_unavailable"}
    try:
        manifest = path / "metadata.json"
        if path.is_symlink() or path.is_junction() or manifest.is_symlink() or manifest.is_junction():
            return unavailable
        if not manifest.is_file() or not 0 < manifest.stat().st_size <= 65536:
            return unavailable
        with manifest.open("rb") as stream:
            payload = stream.read(65537)
        if len(payload) > 65536:
            return unavailable
        if expected is not None and hashlib.sha256(payload).hexdigest() != expected.metadata_sha256:
            return unavailable
        metadata = json.loads(payload)
        if not isinstance(metadata, dict):
            return unavailable
        if (
            type(metadata.get("schema_version")) is not int or metadata["schema_version"] not in {1, 2, 3}
            or metadata.get("algorithm") not in ALGORITHMS.values()
            or metadata.get("runtime") != RUNTIME
            or not isinstance(metadata.get("files"), dict) or set(metadata["files"]) != set(FILE_LIMITS)
            or not isinstance(metadata.get("model_version"), str)
            or re.fullmatch(r"[0-9a-f]{64}", metadata["model_version"]) is None
        ):
            return unavailable
        for filename, size_limit in FILE_LIMITS.items():
            artifact = path / filename
            digest = metadata["files"][filename]
            if (
                not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or artifact.is_symlink() or artifact.is_junction() or not artifact.is_file()
                or not 0 < artifact.stat().st_size <= size_limit
            ):
                return unavailable
    except (OSError, ValueError, TypeError):
        return unavailable
    return {
        "status": "configured", "reason": "lazy_model_load_pending", "validation": "manifest",
        "model_loaded": False, "expected_manifest_matched": expected is not None,
    }


async def _persona_capability(adapter: Any, expected: "ExpectedArtifactManifest | None" = None) -> dict[str, Any]:
    readiness = getattr(adapter, "readiness", None)
    if callable(readiness):
        try:
            result = readiness()
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, Mapping) and result.get("status") in {"configured", "available", "unavailable", "unknown"}:
                return {"status": result["status"], "reason": result.get("reason")}
        except Exception:
            logger.warning("Persona artifact readiness is unavailable")
            return {"status": "unavailable", "reason": "artifact_unavailable"}
    path = getattr(adapter, "artifact_dir", None)
    if isinstance(path, Path):
        return _manifest_capability(path, expected)
    return {"status": "unknown", "reason": "manifest_readiness_not_supported"}



from alembic.config import Config
from alembic.runtime.migration import MigrationContext

from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine
from bebshax.db.engine import normalize_async_database_url


async def check_migrations_current_async(database_url: str, alembic_ini_path: str = "alembic.ini") -> None:
    """Strict standalone revision check; startup uses db.engine.init_database."""
    ini = (
        Path(__file__).resolve().parents[1] / "alembic.ini"
        if alembic_ini_path == "alembic.ini" else Path(alembic_ini_path).resolve()
    )
    if not ini.is_file():
        raise RuntimeError("Alembic configuration is unavailable")
    alembic_cfg = Config(str(ini))
    location = Path(alembic_cfg.get_main_option("script_location", "alembic"))
    if not location.is_absolute():
        location = ini.parent / location
    alembic_cfg.set_main_option("script_location", str(location.resolve()))
    script = ScriptDirectory.from_config(alembic_cfg)
    head_revisions = set(script.get_heads())
    if len(head_revisions) != 1:
        raise RuntimeError("Alembic scripts must have exactly one migration head")

    async_url = normalize_async_database_url(database_url)
    engine = create_async_engine(async_url, hide_parameters=True)

    def _get_current(sync_conn):
        ctx = MigrationContext.configure(sync_conn)
        return set(ctx.get_current_heads())

    try:
        async with engine.connect() as conn:
            current_revisions = await conn.run_sync(_get_current)
    finally:
        await engine.dispose()

    if current_revisions != head_revisions:
        raise SystemExit("Database schema is not at the current Alembic head; run alembic upgrade head")


def check_migrations_current(sync_database_url: str, alembic_ini_path: str = "alembic.ini") -> None:
    """Sync wrapper for tests and external scripts."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Fallback if called inside an event loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.submit(asyncio.run, check_migrations_current_async(sync_database_url, alembic_ini_path)).result()
    else:
        asyncio.run(check_migrations_current_async(sync_database_url, alembic_ini_path))


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    from bebshax.db.capacity_state import (
        CooldownStore, load_recent_route_observations, load_todays_provenance,
    )
    from bebshax.llm.quota import QuotaLedger, quota_aware_ranker
    app.state.core_ready = False
    app.state.database_revision_validated = False
    tasks = RuntimeTaskRegistry(settings.runtime_shutdown_timeout_s)
    app.state.register_runtime_task = tasks.register

    async with AsyncExitStack() as resources:
        registered: set[int] = set()

        def register_resource(resource: Any) -> Any:
            if id(resource) not in registered:
                registered.add(id(resource))
                resources.push_async_callback(_close_resource, resource, settings.runtime_shutdown_timeout_s)
            return resource

        app.state.register_runtime_resource = register_resource
        try:
            db_engine = create_engine(settings)
            resources.push_async_callback(db_engine.dispose)
            sessionmaker_ = create_async_sessionmaker(db_engine)
            try:
                await init_database(db_engine, sessionmaker_, seed=settings.demo_mode)
            except SchemaValidationError as exc:
                # Revision/schema messages name schema state, never credentials.
                logger.error("Database startup validation failed: %s", exc)
                raise RuntimeError(
                    "Database initialization failed; verify connectivity and apply the current Alembic head"
                ) from None
            except Exception as exc:
                # Driver errors can echo the DSN; the class alone tells connectivity from auth.
                logger.error("Database startup validation failed: %s", type(exc).__name__)
                raise RuntimeError(
                    "Database initialization failed; verify connectivity and apply the current Alembic head"
                ) from None
            app.state.database_revision_validated = True
            app.state.db_sessionmaker = sessionmaker_

            processing_policy = effective_processing_policy(settings)
            app.state.remote_processing_policy = processing_policy
            exported = export_provider_credentials()
            if exported:
                logger.info("Provider credentials loaded from .env: %s", sorted(exported))

            ledger = QuotaLedger()
            cooldown_store = register_resource(CooldownStore(sessionmaker_))
            try:
                records = await load_todays_provenance(sessionmaker_)
                ledger.seed_provenance(records)
                initial_cooldowns = await cooldown_store.load_active()
                observations = await load_recent_route_observations(sessionmaker_)
            except Exception:
                logger.error("Runtime capacity restore failed")
                raise RuntimeError("Runtime capacity state could not be restored") from None

            adapters = build_default_adapters(
                quota_ledger=ledger, provider_config=settings.provider_config_path,
                initial_cooldowns=initial_cooldowns, on_cooldown_change=cooldown_store.persist,
            )
            for adapter in adapters.values():
                register_resource(adapter)
            primary = adapters.get("freellmpool")
            seed_metrics = getattr(primary, "seed_metrics", None)
            if observations and callable(seed_metrics):
                await seed_metrics(observations)

            sink = ProvenanceSink(sessionmaker_)
            resources.push_async_callback(sink.stop)
            await sink.start()

            async def _on_provenance(record: ProvenanceRecord) -> None:
                try:
                    ledger.record(record)
                    record_provider_observations(app, record)
                finally:
                    await sink.persist(record)

            llm_router = register_resource(PoolRouter(
                adapters, on_provenance=_on_provenance, ranker=quota_aware_ranker(ledger),
                initial_cooldowns=initial_cooldowns, on_cooldown_change=cooldown_store.persist,
                processing_policy=processing_policy,
            ))
            app.state.quota_ledger = ledger
            app.state.cooldown_store = cooldown_store
            app.state.llm_adapters = adapters
            app.state.llm_router = llm_router
            app.state.llm_service = llm_router
            app.state.provider_health = {}
            app.state.provider_health_snapshot = lambda: provider_status_snapshot(app)
            for record in records:
                record_provider_observations(app, record)
            app.state.provenance_sink = sink
            app.state.persona_ml = register_resource(_build_persona_model(settings))

            async def persona_capability_snapshot() -> dict[str, Any]:
                capability = await _persona_capability(app.state.persona_ml, settings.expected_ml_persona_manifest)
                app.state.persona_capability = capability
                return capability

            app.state.persona_capability_snapshot = persona_capability_snapshot
            app.state.persona_capability = await persona_capability_snapshot()
            app.state.persona_required = settings.ml_persona_required
            if settings.ml_persona_required and app.state.persona_capability["status"] not in {"configured", "available"}:
                raise RuntimeError("Required persona capability is unavailable")
            app.state.persona_engine = register_resource(PersonaEngine(
                llm_router, EvidenceStore(), ml_generator=app.state.persona_ml,
            ))
            embedding_options = {}
            if settings.embedding_backend == "freellmpool":
                if "provider_config" not in inspect.signature(build_embedding_backend).parameters:
                    raise RuntimeError("Remote embeddings require a factory with explicit provider configuration")
                embedding_options["provider_config"] = settings.provider_config_path
                embedding_options["processing_policy"] = processing_policy
            embeddings = register_resource(build_embedding_backend(
                settings.embedding_backend, settings.embedding_model, **embedding_options,
            ))
            app.state.memory_service = register_resource(MemoryService(sessionmaker_, embeddings, llm=llm_router))
            app.state.interview_engine = register_resource(InterviewEngine(
                llm_router, sessionmaker_, memory=app.state.memory_service, suggest_questions=True,
            ))
            from bebshax.behavioral.engine import BehavioralSimulationEngine
            app.state.behavioral_engine = register_resource(BehavioralSimulationEngine(
                llm_router, sessionmaker_, memory=app.state.memory_service,
            ))
            await job_api.initialize_jobs(app)
            app.state.core_ready = True
            yield
        finally:
            app.state.core_ready = False
            try:
                try:
                    job_runtime = getattr(app.state, "job_runtime", None)
                    if job_runtime is not None:
                        await job_runtime.shutdown(timeout_s=min(settings.runtime_shutdown_timeout_s, 60))
                finally:
                    await tasks.aclose()
            except BaseException:
                resources = resources.pop_all()
                app.state.runtime_shutdown_status = "degraded"
                logger.error("Runtime shutdown failed; retaining resources until child tasks drain")

                async def cleanup_after_drain() -> None:
                    await tasks.drain()
                    await resources.aclose()

                def cleanup_finished(task: asyncio.Task[None]) -> None:
                    if task.cancelled() or task.exception() is not None:
                        app.state.runtime_shutdown_status = "cleanup_failed"
                        logger.error("Deferred runtime resource cleanup failed")

                cleanup = asyncio.create_task(cleanup_after_drain(), name="bebshax-runtime-cleanup")
                app.state.runtime_cleanup_task = cleanup
                cleanup.add_done_callback(cleanup_finished)
                raise


def create_app() -> FastAPI:
    settings = fail_fast_on_invalid_settings()
    # Apply the configured level only when nothing else owns logging (uvicorn's
    # log-config, pytest, or an embedding process win when they installed handlers).
    if not logging.getLogger().handlers:
        logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    # The interactive docs and schema enumerate every route for anonymous callers;
    # hosted environments serve the API only.
    hosted = settings.environment in ("production", "staging")
    app = FastAPI(
        title=settings.app_name, version=__version__, lifespan=_lifespan,
        docs_url=None if hosted else "/docs", redoc_url=None if hosted else "/redoc",
        openapi_url=None if hosted else "/openapi.json",
    )
    app.state.settings = settings

    app.state.limiter = limiter
    # One envelope for every error body ({detail, error_code, request_id, ...});
    # this also replaces slowapi's default 429 handler.
    register_exception_handlers(app)
    app.add_middleware(SlowAPIMiddleware)
    # Inside CORS so a browser can read the 500 envelope (request_id included)
    # instead of an opaque network error; the Starlette handler stays as backstop.
    app.add_middleware(UnhandledExceptionEnvelopeMiddleware)
    # Inside CORS so a browser can still read the 413 envelope.
    app.add_middleware(BodySizeLimitMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        # Any *.vercel.app / *.onrender.com origin used to match here, which with
        # allow_credentials=True let anyone's free deployment read a logged-in
        # user's data. Deployed frontends belong in BEBSHAX_CORS_ORIGINS.
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )

    @app.middleware("http")
    async def _security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # HSTS is inert over plain HTTP, so it is safe for local/demo runs and
        # active the moment the API is served over TLS. CSP is deliberately NOT
        # set here: the built frontend is served by a separate nginx origin and
        # its inline/style surface is unverified from this process, so a policy
        # written blind would risk blanking the UI at the exhibition.
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
        return response

    # Outermost user middleware: every response (CORS preflights included)
    # carries X-Request-ID and produces exactly one access-log line.
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router)
    app.include_router(routes_router, prefix="/api")
    app.include_router(personas_router, prefix="/api")
    app.include_router(interviews_router, prefix="/api")
    from bebshax.api.behavioral import router as behavioral_router
    app.include_router(behavioral_router, prefix="/api")
    app.include_router(copilot_router, prefix="/api")
    app.include_router(studies_router, prefix="/api")
    app.include_router(evaluation_router, prefix="/api")

    # OpenRouter health verification & Dataset Sources
    from bebshax.api.ai_review import router as ai_review_router
    from bebshax.api.datasets import router as datasets_router
    from bebshax.api.demo_lab import router as demo_lab_router
    from bebshax.api.openrouter_health import router as openrouter_health_router
    from bebshax.api.evidence import router as evidence_router
    from bebshax.api.segmentation import router as segmentation_router
    from bebshax.api.payments import router as payments_router

    app.include_router(openrouter_health_router, prefix="/api")
    app.include_router(datasets_router, prefix="/api")
    app.include_router(evidence_router, prefix="/api")
    app.include_router(segmentation_router, prefix="/api")
    app.include_router(payments_router, prefix="/api")
    app.include_router(ai_review_router, prefix="/api")
    # Judge Lab: always mounted, but every route 404s unless demo_mode or a
    # development environment (see demo_lab.require_demo_lab) — not discoverable in prod.
    app.include_router(demo_lab_router, prefix="/api")
    return app


app = create_app()

