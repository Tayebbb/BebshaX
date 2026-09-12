import asyncio
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update


RUN_URL = "/api/studies/study-1/behavioral-tests/test-1/runs"
OWNER = {"X-Test-Owner": "owner-1"}


async def test_behavioral_execution_requires_authentication(behavioral_jobs_app) -> None:
    fixture = behavioral_jobs_app
    async with AsyncClient(transport=ASGITransport(app=fixture.app), base_url="http://test") as client:
        response = await client.post(RUN_URL, json={})
    assert response.status_code == 401
    assert fixture.fake.calls == 0


async def test_behavioral_registry_uses_ten_minute_deadline_and_deduplicates(behavioral_jobs_app) -> None:
    fixture = behavioral_jobs_app
    headers = {**OWNER, "Idempotency-Key": "behavioral-command"}
    async with AsyncClient(transport=ASGITransport(app=fixture.app), base_url="http://test") as client:
        response = await client.post(RUN_URL, json={}, headers=headers)
        assert response.status_code == 201
        run = response.json()
        await asyncio.wait_for(fixture.app.state.job_runtime.drain(), 2)
        duplicate = await client.post(RUN_URL, json={}, headers=headers)
        assert duplicate.status_code == 201
        assert duplicate.json()["job_id"] == run["job_id"]
        assert fixture.fake.calls == 1
    job = await fixture.store.get(run["job_id"], kind="behavioral_simulation", scope_id="study-1", owner_id="owner-1")
    assert job["state"] == "completed"
    duration = datetime.fromisoformat(job["deadline_at"]) - datetime.fromisoformat(job["started_at"])
    assert duration.total_seconds() == 600


async def test_behavioral_idempotency_conflicts_after_persona_revision_changes(behavioral_jobs_app) -> None:
    from bebshax.db.models import Personas

    fixture = behavioral_jobs_app
    headers = {**OWNER, "Idempotency-Key": "revision-command"}
    async with AsyncClient(transport=ASGITransport(app=fixture.app), base_url="http://test") as client:
        response = await client.post(RUN_URL, json={}, headers=headers)
        assert response.status_code == 201
        await asyncio.wait_for(fixture.app.state.job_runtime.drain(), 2)
        async with fixture.maker() as session, session.begin():
            await session.execute(update(Personas).where(Personas.id == "persona-1").values(version=2))
        changed = await client.post(RUN_URL, json={}, headers=headers)
    assert changed.status_code == 409
    assert fixture.fake.calls == 1


@pytest.mark.parametrize("payload", [
    {"scenario_text": "x" * 10001},
    {"parameters": {"script": "x" * 65537}},
    {"target_population_type": "selected_personas", "target_persona_ids": ["x" * 65]},
    {"target_persona_ids": ["persona-1"] * 51},
])
async def test_behavioral_script_and_population_inputs_are_bounded(behavioral_jobs_app, payload) -> None:
    from bebshax.jobs.orm import DurableJobs

    fixture = behavioral_jobs_app
    async with AsyncClient(transport=ASGITransport(app=fixture.app), base_url="http://test") as client:
        response = await client.post(RUN_URL, json=payload, headers=OWNER)
    assert response.status_code == 422
    assert fixture.fake.calls == 0
    async with fixture.maker() as session:
        assert await session.scalar(select(func.count()).select_from(DurableJobs)) == 0


async def test_behavioral_cancellation_persists_run_and_owner_scoped_job(behavioral_jobs_app) -> None:
    from bebshax.behavioral.orm import BehavioralTestRuns

    fixture = behavioral_jobs_app
    fixture.fake.release.clear()
    async with AsyncClient(transport=ASGITransport(app=fixture.app), base_url="http://test") as client:
        response = await client.post(RUN_URL, json={}, headers=OWNER)
        assert response.status_code == 201
        run = response.json()
        await asyncio.wait_for(fixture.fake.started.wait(), 2)
        cancel_url = f"/api/studies/study-1/behavioral-tests/runs/{run['id']}/cancel"
        foreign = await client.post(cancel_url, headers={"X-Test-Owner": "owner-2"})
        assert foreign.status_code in (403, 404)
        cancelled = await client.post(cancel_url, headers=OWNER)
        assert cancelled.status_code == 200
        await asyncio.wait_for(fixture.app.state.job_runtime.drain(), 2)
    job = await fixture.store.get(run["job_id"], kind="behavioral_simulation", scope_id="study-1", owner_id="owner-1")
    assert job["state"] == "cancelled"
    assert job["provider_outcome_unknown"] is True
    async with fixture.maker() as session:
        saved_run = await session.get(BehavioralTestRuns, run["id"])
        assert saved_run.status == "cancelled"