from collections.abc import AsyncIterator
import asyncio
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from bebshax.jobs.orm import DurableJobs, JobAttempts, JobCheckpoints, JobOwners
from bebshax.jobs.store import SQLJobStore


@pytest.fixture
async def journal_engine() -> AsyncIterator[AsyncEngine]:
    database_path = Path(__file__).with_name(f".jobs-fixture-{uuid.uuid4().hex}.sqlite")
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(connection, record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    tables = [model.__table__ for model in (JobOwners, DurableJobs, JobAttempts, JobCheckpoints)]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: JobOwners.metadata.create_all(sync, tables=tables))
    try:
        yield engine
    finally:
        await engine.dispose()
        database_path.unlink(missing_ok=True)


@pytest.fixture
def job_store(journal_engine: AsyncEngine) -> SQLJobStore:
    return SQLJobStore(async_sessionmaker(journal_engine, expire_on_commit=False))


@pytest.fixture
async def sql_upload_context(
    journal_engine: AsyncEngine, job_store: SQLJobStore, monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[SimpleNamespace]:
    from unittest.mock import patch

    from fastapi import FastAPI, Request

    from bebshax.api.jobs import shutdown_jobs
    from bebshax.api.upload_admission import UploadAdmission

    with patch("dotenv.load_dotenv", return_value=False), patch(
        "pydantic_settings.sources.DotEnvSettingsSource._read_env_files", return_value={}
    ), patch(
        "pydantic_settings.sources.EnvSettingsSource._load_env_vars",
        return_value={"bebshax_jwt_secret": "test-only-upload-sql-signing-material-0123456789"},
    ):
        from bebshax.api import auth
        from bebshax.auth import security
        from bebshax.auth.models import Users

    settings = SimpleNamespace(
        jwt_secret="test-only-upload-sql-signing-material-0123456789",
        jwt_secret_previous=None, jwt_expire_days=1,
        jwt_issuer="test-upload-sql", jwt_audience="test-upload-client",
        email_verification_enforced=True,
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    async with journal_engine.begin() as connection:
        await connection.run_sync(lambda sync: Users.__table__.create(sync, checkfirst=True))
    async with job_store.sessionmaker() as session:
        session.add_all([
            Users(
                id=owner_id, email=f"{owner_id}@example.test", full_name="Synthetic Upload Owner",
                is_active=True, is_verified=True, session_version=2,
            )
            for owner_id in ("owner-1", "owner-2")
        ])
        await session.commit()

    app = FastAPI()
    app.state.db_sessionmaker = job_store.sessionmaker
    app.state.job_store = job_store

    def upload_request(owner_id: str = "owner-1") -> Request:
        token = security.create_access_token(owner_id, session_version=2)
        return Request({
            "type": "http", "app": app, "method": "POST", "path": "/api/datasets/upload",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "query_string": b"", "root_path": "", "scheme": "http",
            "server": ("testserver", 80), "client": ("127.0.0.1", 12000),
        })

    try:
        yield SimpleNamespace(app=app, admission=UploadAdmission(), request=upload_request)
    finally:
        await shutdown_jobs(app)


@pytest.fixture
def held_upload_job_counts(job_store: SQLJobStore, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    control = SimpleNamespace(enabled=True, waiters=asyncio.Queue())
    original_count = job_store.running_count

    async def paused_count(owner_id: str) -> int:
        count = await original_count(owner_id)
        if control.enabled:
            release = asyncio.Event()
            control.waiters.put_nowait(release)
            await release.wait()
        return count

    monkeypatch.setattr(job_store, "running_count", paused_count)
    return control


@pytest.fixture
async def behavioral_jobs_app(journal_engine, job_store, monkeypatch):
    from fastapi import FastAPI, HTTPException, Request
    from pydantic_settings import DotEnvSettingsSource

    monkeypatch.setattr(DotEnvSettingsSource, "_read_env_files", lambda source: {})
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", "jobs-fixture-only-not-a-real-secret-0123456789")
    from bebshax.api import auth, behavioral
    from bebshax.api.deps import get_session
    from bebshax.api.jobs import shutdown_jobs
    from bebshax.auth.models import Users
    from bebshax.behavioral.orm import (
        BehavioralInsights, BehavioralTestResults, BehavioralTestRuns, BehavioralTestScenarios, BehavioralTests,
    )
    from bebshax.datasets.orm import DatasetVersions
    from bebshax.db.models import Businesses, Personas, Studies

    async with journal_engine.begin() as connection:
        await connection.run_sync(DatasetVersions.metadata.create_all)
    maker = job_store.sessionmaker
    owner = Users(id="owner-1", email="owner1@example.test", full_name="Synthetic Owner")
    other_owner = Users(id="owner-2", email="owner2@example.test", full_name="Synthetic Other Owner")
    async with maker() as session:
        session.add_all([owner, other_owner])
        await session.flush()
        session.add(Studies(id="study-1", user_id=owner.id, title="Synthetic study"))
        session.add(Personas(id="persona-1", study_id="study-1", user_id=owner.id, owner_id=owner.id, name="Synthetic Persona", version=1))
        session.add(BehavioralTests(id="test-1", study_id="study-1", user_id=owner.id, name="Price", test_type="pricing_test"))
        await session.flush()
        session.add(BehavioralTestScenarios(
            id="scenario-1", behavioral_test_id="test-1", title="A synthetic offer", scenario_text="Would this synthetic offer be useful?",
        ))
        await session.commit()

    class FakeBehavioralEngine:
        def __init__(self):
            self.calls = 0
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.release.set()

        async def execute_test_run(self, *, run_id, user_id, job):
            self.calls += 1
            await job.begin_item("synthetic-provider-attempt", input_data={"run_id": run_id})
            self.started.set()
            await self.release.wait()
            async with maker() as session, session.begin():
                await job.fence(session)
                run = await session.get(BehavioralTestRuns, run_id)
                run.status = "completed"
                run.completed_count = 1
                await job.complete_item("synthetic-provider-attempt", result_refs={"run_id": run_id}, session=session)
            return run

        async def retry_failed_simulations(self, run_id, *, study_id, user_id, job):
            return await self.execute_test_run(run_id=run_id, user_id=user_id, job=job)

    async def session_dependency():
        async with maker() as session:
            yield session

    async def optional_owner(request: Request):
        return {"owner-1": owner, "owner-2": other_owner}.get(request.headers.get("X-Test-Owner"))

    async def required_owner(request: Request):
        user = await optional_owner(request)
        if user is None:
            raise HTTPException(401, "Authentication required")
        return user

    app = FastAPI()
    app.include_router(behavioral.router, prefix="/api")
    app.dependency_overrides[get_session] = session_dependency
    app.dependency_overrides[auth.get_optional_current_user] = optional_owner
    app.dependency_overrides[auth.get_current_user] = required_owner
    monkeypatch.setattr(behavioral.limiter, "enabled", False)
    fake = FakeBehavioralEngine()
    app.state.db_sessionmaker = maker
    app.state.job_store = job_store
    app.state.behavioral_engine = fake
    try:
        yield SimpleNamespace(app=app, maker=maker, fake=fake, store=job_store)
    finally:
        fake.release.set()
        await shutdown_jobs(app)