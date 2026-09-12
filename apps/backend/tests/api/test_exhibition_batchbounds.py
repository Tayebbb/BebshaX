"""Batch interview jobs must share admission limits and terminate within their budget."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from bebshax.api import interviews as interviews_api
from bebshax.api.auth import get_optional_current_user
from bebshax.api.jobs import start_job_async
from bebshax.auth.models import Users
from bebshax.db.models import Personas, Studies
from bebshax.interview.orm import Conversations


_BATCH_URL = "/api/studies/exhibition_batch_study/interviews/batch-run"


def _job_tasks(app):
    return set(getattr(app.state, "async_job_tasks", set())) | set(
        getattr(app.state, "interview_batch_tasks", set())
    )


def _jobs_finished(client, timeout_s=2.0):
    async def wait_for_jobs():
        tasks = _job_tasks(client.app)
        if not tasks:
            return True
        _, pending = await asyncio.wait(tasks, timeout=timeout_s)
        return not pending

    return client.portal.call(wait_for_jobs)


@pytest.fixture
async def exhibition_batch_case(api_test_app, monkeypatch):
    owner = Users(id="exhibition_batch_owner", email="batch-owner@example.test", full_name="Batch Owner", is_verified=True)
    visitor = Users(id="exhibition_batch_visitor", email="batch-visitor@example.test", full_name="Batch Visitor", is_verified=True)
    async with api_test_app.app.state.db_sessionmaker() as session:
        session.add_all([owner, visitor])
        await session.flush()
        session.add_all([
            Studies(
                id="exhibition_batch_study", user_id=owner.id, title="Batch fixture",
                script_questions=["A synthetic question"],
            ),
            Studies(
                id="exhibition_batch_other_study", user_id=visitor.id, title="Other batch fixture",
                script_questions=["Another synthetic question"],
            ),
        ])
        await session.flush()
        session.add_all([
            Personas(
                id=f"exhibition_batch_persona_{index}", name=f"Synthetic Batch Persona {index}",
                study_id="exhibition_batch_study", owner_id=owner.id,
            )
            for index in range(2)
        ])
        session.add(Personas(
            id="exhibition_batch_other_persona", name="Other Synthetic Persona",
            study_id="exhibition_batch_other_study", owner_id=visitor.id,
        ))
        await session.commit()

    async def blocked_question(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(interviews_api.limiter, "enabled", False)
    monkeypatch.setattr(api_test_app.app.state.interview_engine, "ask", AsyncMock(side_effect=blocked_question))
    monkeypatch.setattr(api_test_app.app.state.interview_engine, "complete", AsyncMock(return_value={"insights_dropped": 0}))
    api_test_app.app.dependency_overrides[get_optional_current_user] = lambda: owner
    yield api_test_app, {"owner": owner, "visitor": visitor, "anonymous": None}

    async def cancel_jobs():
        tasks = _job_tasks(api_test_app.app)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    api_test_app.portal.call(cancel_jobs)
    api_test_app.app.dependency_overrides.pop(get_optional_current_user, None)


def test_batch_respects_jobs_running_in_other_features(exhibition_batch_case):
    client, users = exhibition_batch_case

    async def blocked_job(job):
        await asyncio.Event().wait()

    async def seed_jobs():
        for index in range(3):
            await start_job_async(
                client.app, kind="persona_generation", scope_id=f"synthetic_scope_{index}",
                runner=blocked_job, user_id=users["owner"].id, input_data={"index": index},
            )

    client.portal.call(seed_jobs)

    response = client.post(_BATCH_URL, json={})

    assert response.status_code == 429, response.text
    assert response.json()["error_code"] == "too_many_jobs"
    assert response.json()["max_running_jobs"] == 3


def test_fourth_active_batch_is_denied_without_blocking_another_owner(exhibition_batch_case):
    client, users = exhibition_batch_case
    for _ in range(3):
        accepted = client.post(_BATCH_URL, json={})
        assert accepted.status_code == 202, accepted.text
        assert accepted.json()["job_id"].startswith("bjob_")
        assert set(accepted.json()) == {"job_id", "study_id", "status", "total_personas", "personas"}

    rejected = client.post(_BATCH_URL, json={})

    assert rejected.status_code == 429, rejected.text
    assert rejected.json()["error_code"] == "too_many_jobs"
    client.app.dependency_overrides[get_optional_current_user] = lambda: users["visitor"]
    other = client.post("/api/studies/exhibition_batch_other_study/interviews/batch-run", json={})
    assert other.status_code == 202, other.text


def test_batch_deadline_terminates_pending_work_and_reports_failure(exhibition_batch_case, monkeypatch):
    client, _ = exhibition_batch_case
    monkeypatch.setattr(interviews_api, "_BATCH_JOB_TIMEOUT_S", 0.01, raising=False)

    response = client.post(_BATCH_URL, json={})

    assert response.status_code == 202, response.text
    assert _jobs_finished(client, timeout_s=1.0), "The batch exceeded its configured deadline"
    polled = client.get(f"{_BATCH_URL}/{response.json()['job_id']}")
    assert polled.status_code == 200, polled.text
    job = polled.json()
    assert job["status"] == "failed"
    assert job["error_code"] == "job_timeout"
    assert job["finished_at"] is not None
    assert job["completed_count"] == 0
    assert job["failed_count"] == job["total_personas"] == 2
    assert {entry["status"] for entry in job["personas"].values()} == {"failed"}


def test_running_jobs_are_not_evicted_out_of_the_admission_count(exhibition_batch_case):
    client, users = exhibition_batch_case

    async def blocked_job(job):
        await asyncio.Event().wait()

    async def seed_jobs():
        for index in range(51):
            await start_job_async(
                client.app, kind="persona_generation", scope_id=f"synthetic_scope_{index}",
                runner=blocked_job, input_data={"index": index},
                user_id=users["owner"].id if index < 3 else f"synthetic_owner_{index}",
            )

    client.portal.call(seed_jobs)

    response = client.post(_BATCH_URL, json={})

    assert response.status_code == 429, response.text
    assert response.json()["error_code"] == "too_many_jobs"


@pytest.mark.parametrize("caller", ["anonymous", "visitor"])
async def test_private_batch_status_stays_private_after_study_becomes_shared(exhibition_batch_case, caller):
    client, users = exhibition_batch_case
    response = client.post(_BATCH_URL, json={})
    assert response.status_code == 202, response.text
    async with client.app.state.db_sessionmaker() as session:
        study = await session.get(Studies, "exhibition_batch_study")
        study.is_demo = True
        await session.commit()
    client.app.dependency_overrides[get_optional_current_user] = lambda: users[caller]

    polled = client.get(f"{_BATCH_URL}/{response.json()['job_id']}")

    assert polled.status_code == 404, polled.text
    assert "Synthetic Batch Persona" not in polled.text


@pytest.mark.parametrize("failed_personas, expected_status", [
    (set(), "completed"),
    ({"exhibition_batch_persona_0"}, "completed_with_failures"),
    ({"exhibition_batch_persona_0", "exhibition_batch_persona_1"}, "failed"),
])
def test_batch_terminal_status_and_counts_remain_compatible(
    exhibition_batch_case, monkeypatch, failed_personas, expected_status
):
    client, _ = exhibition_batch_case

    async def answer(conversation_id, question, **_governance):
        async with client.app.state.db_sessionmaker() as session:
            conversation = await session.get(Conversations, conversation_id)
            if conversation.persona_id in failed_personas:
                raise RuntimeError("private-internal-error-detail")

    monkeypatch.setattr(client.app.state.interview_engine, "ask", AsyncMock(side_effect=answer))

    response = client.post(_BATCH_URL, json={})

    assert response.status_code == 202, response.text
    assert _jobs_finished(client)
    polled = client.get(f"{_BATCH_URL}/{response.json()['job_id']}")
    assert polled.status_code == 200, polled.text
    job = polled.json()
    assert job["status"] == expected_status
    assert job["failed_count"] == len(failed_personas)
    assert job["completed_count"] == 2 - len(failed_personas)
    assert job["question_count"] == 1
    assert job["finished_at"] is not None
    assert "private-internal-error-detail" not in polled.text
    assert "kind" not in job


@pytest.mark.parametrize("bound", ["persona_count", "question_count", "question_length"])
async def test_inherited_batch_inputs_obey_request_limits(exhibition_batch_case, bound):
    client, users = exhibition_batch_case
    async with client.app.state.db_sessionmaker() as session:
        if bound == "persona_count":
            session.add_all([
                Personas(
                    id=f"exhibition_batch_persona_{index}", name=f"Synthetic Batch Persona {index}",
                    study_id="exhibition_batch_study", owner_id=users["owner"].id,
                )
                for index in range(2, 51)
            ])
        else:
            study = await session.get(Studies, "exhibition_batch_study")
            study.script_questions = ["Question"] * 21 if bound == "question_count" else ["Q" * 2001]
        await session.commit()

    response = client.post(_BATCH_URL, json={})

    assert response.status_code == 422
    assert response.json()["error_code"] == "batch_limit_exceeded"
    client.app.state.interview_engine.ask.assert_not_awaited()
    assert not _job_tasks(client.app)


async def test_explicit_batch_at_request_limits_is_accepted(exhibition_batch_case):
    client, users = exhibition_batch_case
    async with client.app.state.db_sessionmaker() as session:
        session.add_all([
            Personas(
                id=f"exhibition_batch_persona_{index}", name=f"Synthetic Batch Persona {index}",
                study_id="exhibition_batch_study", owner_id=users["owner"].id,
            )
            for index in range(2, 50)
        ])
        await session.commit()

    response = client.post(_BATCH_URL, json={
        "persona_ids": [f"exhibition_batch_persona_{index}" for index in range(50)],
        "questions": ["Q" * 2000 for _ in range(20)],
    })

    assert response.status_code == 202, response.text
    assert response.json()["total_personas"] == 50


@pytest.mark.parametrize("foreign_owner", ["usr_system_holder", "exhibition_batch_visitor"])
@pytest.mark.parametrize("targeted", [False, True])
async def test_batch_cannot_interview_foreign_owned_persona_under_own_study(
    exhibition_batch_case, foreign_owner, targeted
):
    client, _ = exhibition_batch_case
    async with client.app.state.db_sessionmaker() as session:
        persona = await session.get(Personas, "exhibition_batch_persona_1")
        persona.owner_id = foreign_owner
        await session.commit()

    response = client.post(
        _BATCH_URL,
        json={"persona_ids": ["exhibition_batch_persona_1"]} if targeted else {},
    )

    assert response.status_code == 403, response.text
    client.app.state.interview_engine.ask.assert_not_awaited()
    assert not _job_tasks(client.app)


def test_batch_cancellation_preserves_completed_interviews(exhibition_batch_case, monkeypatch):
    client, _ = exhibition_batch_case
    second_started = asyncio.Event()
    calls = 0

    async def answer_then_block(conversation_id, question, **_governance):
        nonlocal calls
        calls += 1
        if calls == 2:
            second_started.set()
            await asyncio.Event().wait()

    async def cancel_after_first_completed():
        await asyncio.wait_for(second_started.wait(), timeout=2.0)
        tasks = _job_tasks(client.app)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    monkeypatch.setattr(client.app.state.interview_engine, "ask", AsyncMock(side_effect=answer_then_block))
    response = client.post(_BATCH_URL, json={})
    assert response.status_code == 202, response.text
    client.portal.call(cancel_after_first_completed)

    polled = client.get(f"{_BATCH_URL}/{response.json()['job_id']}")

    assert polled.status_code == 200, polled.text
    job = polled.json()
    assert job["status"] == "completed_with_failures"
    assert job["completed_count"] == job["failed_count"] == 1
    assert job["finished_at"] is not None
    # The interrupted interview is reported as cancelled (counted as a failure), never faked.
    assert sorted(entry["status"] for entry in job["personas"].values()) == ["cancelled", "completed"]


def test_batch_rejects_persona_belonging_to_another_study(exhibition_batch_case):
    client, _ = exhibition_batch_case

    response = client.post(_BATCH_URL, json={
        "persona_ids": ["exhibition_batch_persona_0", "exhibition_batch_other_persona"],
    })

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "One or more personas do not belong to this study"
    assert not _job_tasks(client.app)


def test_batch_skips_stale_ids_and_runs_the_remaining_valid_personas(exhibition_batch_case):
    client, _ = exhibition_batch_case

    response = client.post(_BATCH_URL, json={
        "persona_ids": ["exhibition_batch_persona_0", "per_no_longer_exists"],
    })

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["total_personas"] == 1
    assert set(body["personas"]) == {"exhibition_batch_persona_0"}