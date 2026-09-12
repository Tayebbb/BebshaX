from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def study_alias_http(sql_upload_context, journal_engine, job_store, monkeypatch):
    from bebshax.api import auth, deps, evidence, studies
    from bebshax.api.errors import APIError
    from bebshax.auth.models import Users
    from bebshax.db.models import Base, Businesses, ResearchRuns, Studies

    async with journal_engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(
            sync, tables=[model.__table__ for model in (Businesses, Studies, ResearchRuns)],
        ))
    maker = job_store.sessionmaker
    async with maker() as session, session.begin():
        owners = {owner.id: owner for owner in await session.scalars(select(Users))}
        session.add_all([
            Studies(id="alias-study", user_id="owner-1", title="Synthetic study", prompt="Synthetic idea"),
            Studies(id="other-study", user_id="owner-2", title="Other synthetic study", prompt="Other idea"),
            Studies(id="demo-study", user_id="owner-2", title="Synthetic demo", is_demo=True),
        ])

    request_sessions = []

    async def session_dependency() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            request_sessions.append(session)
            yield session

    async def optional_owner(request: Request) -> Users | None:
        return owners.get(request.headers.get("X-Test-Owner"))

    async def required_owner(request: Request) -> Users:
        owner = await optional_owner(request)
        if owner is None:
            raise HTTPException(401, "Authentication required")
        return owner

    app = sql_upload_context.app
    app.include_router(studies.router, prefix="/api")
    app.include_router(evidence.router, prefix="/api")
    app.dependency_overrides[deps.get_session] = session_dependency
    app.dependency_overrides[auth.get_current_user] = required_owner
    app.dependency_overrides[auth.get_optional_current_user] = optional_owner
    app.dependency_overrides[deps.get_tenant_user] = required_owner
    app.dependency_overrides[deps.get_optional_tenant_user] = optional_owner
    monkeypatch.setattr(studies.limiter, "enabled", False)

    async def api_error(request: Request, error: APIError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content={
            "detail": error.detail, "error_code": error.error_code, **error.extra,
        })

    app.add_exception_handler(APIError, api_error)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = []
    displaced_runtimes = []

    async def run(session, study, user_id=None, *, job=None, run_id=None):
        calls.append(SimpleNamespace(session=session, in_transaction=session.in_transaction(), job=job, run_id=run_id))
        started.set()
        await release.wait()
        if job is None:
            return SimpleNamespace(
                id="inline-run", status="completed", source_count=0, claim_count=0,
                dataset_candidate_count=0, step_progress={}, error_message=None,
            )
        row = await session.get(ResearchRuns, run_id)
        row.status = "completed"
        await job.fence(session)
        await session.commit()
        return row

    app.state.research_engine = SimpleNamespace(run_study_research=run)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield SimpleNamespace(
                app=app, client=client, maker=maker, store=job_store, started=started,
                release=release, calls=calls, request_sessions=request_sessions,
                displaced_runtimes=displaced_runtimes, auth_request=sql_upload_context.request,
            )
    finally:
        release.set()
        runtime = getattr(app.state, "job_runtime", None)
        if runtime is not None:
            displaced_runtimes.append(runtime)
        for runtime in displaced_runtimes:
            await asyncio.wait_for(runtime.drain(), 5)
            await runtime.shutdown()


@pytest.mark.parametrize("suffix", ["research", "research/run"])
async def test_research_urls_accept_durable_run_before_engine_finishes(study_alias_http, suffix):
    from bebshax.db.models import ResearchRuns
    from bebshax.jobs.orm import DurableJobs

    context = study_alias_http
    pending = asyncio.create_task(context.client.post(
        f"/api/studies/alias-study/{suffix}",
        headers={"X-Test-Owner": "owner-1", "Idempotency-Key": "slow-research"},
    ))
    try:
        await asyncio.wait_for(context.started.wait(), 3)
        finished, _ = await asyncio.wait({pending}, timeout=0.5)
        assert pending in finished, "Research acceptance awaited the engine instead of durable admission"
        response = pending.result()
        assert response.status_code == 202, response.text
        accepted = response.json()
        assert accepted["job_id"] and accepted["id"]
        assert accepted["status"] == "queued"
        assert not context.release.is_set()
        assert len(context.calls) == 1
        assert context.calls[0].session not in context.request_sessions
        assert context.calls[0].in_transaction is False
        async with context.maker() as session:
            job = (await session.scalars(select(DurableJobs))).one()
            run = (await session.scalars(select(ResearchRuns))).one()
            assert job.id == accepted["job_id"]
            assert job.owner_id == run.user_id == "owner-1"
            assert job.result_refs["run_id"] == run.id == accepted["id"]
            assert run.status == "queued"
            assert run.step_progress["summary"]["job_id"] == job.id
    finally:
        context.release.set()
        await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.parametrize("first_suffix, second_suffix", [("research", "research/run"), ("research/run", "research")])
async def test_same_key_across_urls_returns_identical_job_and_run(study_alias_http, first_suffix, second_suffix):
    from bebshax.db.models import ResearchRuns
    from bebshax.jobs.orm import DurableJobs

    context = study_alias_http
    headers = {"X-Test-Owner": "owner-1", "Idempotency-Key": "same-command"}
    first = await context.client.post(f"/api/studies/alias-study/{first_suffix}", headers=headers)
    await asyncio.wait_for(context.started.wait(), 3)
    second = await context.client.post(f"/api/studies/alias-study/{second_suffix}", headers=headers)
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert len(context.calls) == 1
    async with context.maker() as session:
        assert len(list(await session.scalars(select(DurableJobs)))) == 1
        assert len(list(await session.scalars(select(ResearchRuns)))) == 1


@pytest.mark.parametrize("first_suffix, second_suffix", [("research", "research/run"), ("research/run", "research")])
async def test_same_key_conflicts_when_study_input_changes(study_alias_http, first_suffix, second_suffix):
    from bebshax.db.models import ResearchRuns, Studies
    from bebshax.jobs.orm import DurableJobs

    context = study_alias_http
    headers = {"X-Test-Owner": "owner-1", "Idempotency-Key": "changed-command"}
    first = await context.client.post(f"/api/studies/alias-study/{first_suffix}", headers=headers)
    assert first.status_code == 202
    async with context.maker() as session, session.begin():
        await session.execute(update(Studies).where(Studies.id == "alias-study").values(prompt="Changed synthetic idea"))
    second = await context.client.post(f"/api/studies/alias-study/{second_suffix}", headers=headers)
    assert second.status_code == 409
    assert second.json()["error_code"] == "job_idempotency_conflict"
    async with context.maker() as session:
        assert (await session.scalars(select(DurableJobs))).one().id == first.json()["job_id"]
        assert (await session.scalars(select(ResearchRuns))).one().id == first.json()["id"]


async def test_same_idempotency_key_is_isolated_between_owners(study_alias_http):
    from bebshax.db.models import ResearchRuns
    from bebshax.jobs.orm import DurableJobs

    context = study_alias_http
    first = await context.client.post("/api/studies/alias-study/research/run", headers={
        "X-Test-Owner": "owner-1", "Idempotency-Key": "shared-key",
    })
    second = await context.client.post("/api/studies/other-study/research", headers={
        "X-Test-Owner": "owner-2", "Idempotency-Key": "shared-key",
    })
    assert first.status_code == second.status_code == 202
    assert first.json()["job_id"] != second.json()["job_id"]
    assert first.json()["id"] != second.json()["id"]
    async with context.maker() as session:
        assert {job.owner_id for job in await session.scalars(select(DurableJobs))} == {"owner-1", "owner-2"}
        assert {run.user_id for run in await session.scalars(select(ResearchRuns))} == {"owner-1", "owner-2"}


@pytest.mark.parametrize("suffix", ["research", "research/run"])
@pytest.mark.parametrize("study_id, owner_id, status_code", [
    ("alias-study", None, 401),
    ("absent-study", "owner-1", 404),
    ("alias-study", "owner-2", 404),
    ("demo-study", "owner-1", 403),
])
async def test_research_denials_do_not_create_jobs_or_runs(study_alias_http, suffix, study_id, owner_id, status_code):
    from bebshax.db.models import ResearchRuns
    from bebshax.jobs.orm import DurableJobs

    context = study_alias_http
    headers = {"X-Test-Owner": owner_id} if owner_id is not None else {}
    response = await context.client.post(f"/api/studies/{study_id}/{suffix}", headers=headers)
    assert response.status_code == status_code, response.text
    assert not context.calls
    async with context.maker() as session:
        assert not list(await session.scalars(select(DurableJobs)))
        assert not list(await session.scalars(select(ResearchRuns)))


@pytest.mark.parametrize("suffix", ["research", "research/run"])
@pytest.mark.parametrize("key", ["", "x" * 201])
async def test_research_rejects_invalid_idempotency_headers(study_alias_http, suffix, key):
    context = study_alias_http
    response = await context.client.post(f"/api/studies/alias-study/{suffix}", headers={
        "X-Test-Owner": "owner-1", "Idempotency-Key": key,
    })
    assert response.status_code == 422
    assert not context.calls


@pytest.mark.parametrize("suffix", ["research", "research/run"])
async def test_research_accepts_maximum_length_idempotency_key(study_alias_http, suffix):
    context = study_alias_http
    response = await context.client.post(f"/api/studies/alias-study/{suffix}", headers={
        "X-Test-Owner": "owner-1", "Idempotency-Key": "x" * 200,
    })
    assert response.status_code == 202
    assert response.json()["job_id"]


@pytest.mark.parametrize("suffix", ["research", "research/run"])
async def test_research_uses_canonical_bearer_authentication(study_alias_http, suffix):
    from bebshax.api import auth

    context = study_alias_http
    context.app.dependency_overrides.pop(auth.get_current_user)
    rejected = await context.client.post(f"/api/studies/alias-study/{suffix}", headers={
        "X-Test-Owner": "owner-1", "Authorization": "Bearer invalid-synthetic-token",
    })
    assert rejected.status_code == 401
    accepted = await context.client.post(
        f"/api/studies/alias-study/{suffix}", headers=dict(context.auth_request().headers),
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["user_id"] == "owner-1"


@pytest.mark.parametrize("suffix", ["research", "research/run"])
@pytest.mark.parametrize("change, status_code, error_code", [
    ({"prompt": "Changed before admission"}, 409, "research_input_changed"),
    ({"user_id": "owner-2"}, 404, "not_found"),
])
async def test_research_fences_owner_and_input_before_atomic_admission(
    study_alias_http, monkeypatch, suffix, change, status_code, error_code,
):
    from bebshax.db.models import ResearchRuns, Studies
    from bebshax.jobs.orm import DurableJobs

    context = study_alias_http
    admit = context.store.admit

    async def change_before_admission(**kwargs):
        async with context.maker() as session, session.begin():
            await session.execute(update(Studies).where(Studies.id == "alias-study").values(**change))
        return await admit(**kwargs)

    monkeypatch.setattr(context.store, "admit", change_before_admission)
    response = await context.client.post(f"/api/studies/alias-study/{suffix}", headers={"X-Test-Owner": "owner-1"})
    assert response.status_code == status_code
    assert response.json()["error_code"] == error_code
    assert not context.calls
    async with context.maker() as session:
        assert not list(await session.scalars(select(DurableJobs)))
        assert not list(await session.scalars(select(ResearchRuns)))


@pytest.mark.parametrize("suffix", ["research", "research/run"])
async def test_failed_run_insert_rolls_back_job_admission(study_alias_http, suffix):
    from bebshax.db.models import ResearchRuns
    from bebshax.jobs.orm import DurableJobs

    context = study_alias_http

    def fail_insert(mapper, connection, target):
        raise RuntimeError("Synthetic research run insert failure")

    event.listen(ResearchRuns, "before_insert", fail_insert)
    try:
        with pytest.raises(RuntimeError, match="Synthetic research run insert failure"):
            await context.client.post(f"/api/studies/alias-study/{suffix}", headers={"X-Test-Owner": "owner-1"})
    finally:
        event.remove(ResearchRuns, "before_insert", fail_insert)
    assert not context.calls
    async with context.maker() as session:
        assert not list(await session.scalars(select(DurableJobs)))
        assert not list(await session.scalars(select(ResearchRuns)))


@pytest.mark.parametrize("suffix", ["research", "research/run"])
@pytest.mark.parametrize("state", ["queued", "running"])
@pytest.mark.parametrize("operation", ["cancel", "expire"])
async def test_fresh_manager_recovers_research_status_and_cancellation(
    study_alias_http, monkeypatch, suffix, state, operation,
):
    from bebshax.db.models import ResearchRuns
    from bebshax.jobs.orm import DurableJobs
    from bebshax.jobs.runtime import JobRuntime
    from bebshax.jobs.store import SQLJobStore, utcnow

    context = study_alias_http
    claim_started = asyncio.Event()
    claim_release = asyncio.Event()
    claim = context.store.claim

    async def held_claim(*args, **kwargs):
        claim_started.set()
        await claim_release.wait()
        return await claim(*args, **kwargs)

    if state == "queued":
        monkeypatch.setattr(context.store, "claim", held_claim)
    try:
        response = await context.client.post(f"/api/studies/alias-study/{suffix}", headers={"X-Test-Owner": "owner-1"})
        assert response.status_code == 202, response.text
        accepted = response.json()
        await asyncio.wait_for((claim_started if state == "queued" else context.started).wait(), 3)
        context.displaced_runtimes.append(context.app.state.job_runtime)
        context.app.state.job_store = SQLJobStore(context.maker)
        context.app.state.job_runtime = JobRuntime(context.app.state.job_store)
        job_url = f"/api/studies/alias-study/research/jobs/{accepted['job_id']}"
        run_url = f"/api/studies/alias-study/research/{accepted['id']}"
        owner_headers = {"X-Test-Owner": "owner-1"}
        foreign_headers = {"X-Test-Owner": "owner-2"}

        forbidden_status = await context.client.get(job_url, headers=foreign_headers)
        forbidden_cancel = await context.client.post(f"{job_url}/cancel", headers=foreign_headers)
        forbidden_run = await context.client.get(run_url, headers=foreign_headers)
        assert forbidden_status.status_code == forbidden_cancel.status_code == forbidden_run.status_code == 404
        wrong_study = await context.client.get(job_url.replace("alias-study", "other-study"), headers=owner_headers)
        assert wrong_study.status_code == 404
        polled = await context.client.get(job_url, headers=owner_headers)
        assert polled.status_code == 200
        assert polled.json()["state"] == state
        assert polled.json()["result_refs"]["run_id"] == accepted["id"]
        recovered_run = await context.client.get(run_url, headers=owner_headers)
        assert recovered_run.status_code == 200
        assert recovered_run.json()["job_id"] == accepted["job_id"]

        if operation == "cancel":
            terminal = await context.client.post(f"{job_url}/cancel", headers=owner_headers)
            expected_state = "cancelled"
        else:
            async with context.maker() as session, session.begin():
                await session.execute(update(DurableJobs).where(DurableJobs.id == accepted["job_id"]).values(
                    lease_expires_at=utcnow() - timedelta(seconds=1),
                ))
            terminal = await context.client.get(job_url, headers=owner_headers)
            expected_state = "interrupted"
        assert terminal.status_code == 200
        assert terminal.json()["state"] == expected_state
        detail = await context.client.get(run_url, headers=owner_headers)
        assert detail.json()["status"] == expected_state
        async with context.maker() as session:
            run = await session.get(ResearchRuns, accepted["id"])
            assert run.status == expected_state
            assert run.completed_at is not None
    finally:
        claim_release.set()