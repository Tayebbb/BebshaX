"""API hardening: rate-limit coverage of LLM-spending routes, per-user job cap,
and request-body bounds that mirror column widths / spend."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from bebshax.api.limiter import limiter
from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base, PersonaGenerationRuns, Studies


def _limit_str(qualified: str) -> str:
    limits = limiter._route_limits.get(qualified)
    assert limits, f"{qualified} must carry an explicit rate limit"
    return str(limits[0].limit)


# ---------------------------------------------------------------------------
# Config-level: every LLM-spending route carries a limit
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("qualified", "expected"),
    [
        # persona generation
        ("bebshax.api.personas.start_persona_generation_job", "10 per 1 minute"),
        ("bebshax.api.personas.regenerate_study_persona_endpoint", "10 per 1 minute"),
        ("bebshax.api.personas.generate_persona_endpoint", "10 per 1 minute"),
        # reports
        ("bebshax.api.studies.generate_study_report", "10 per 1 minute"),
        ("bebshax.api.studies.start_report_generation_job", "10 per 1 minute"),
        # interviews
        ("bebshax.api.interviews.batch_run_study_interviews", "5 per 1 minute"),
        ("bebshax.api.interviews.post_study_interview_message", "30 per 1 minute"),
        ("bebshax.api.interviews.post_study_interview_message_stream", "30 per 1 minute"),
        ("bebshax.api.interviews.post_message", "30 per 1 minute"),
        ("bebshax.api.interviews.complete_study_interview", "10 per 1 minute"),
        # simulations
        ("bebshax.api.behavioral.trigger_behavioral_test_run", "10 per 1 minute"),
        ("bebshax.api.behavioral.retry_failed_simulations", "10 per 1 minute"),
        ("bebshax.api.segmentation.run_segmentation", "10 per 1 minute"),
        # datasets: LLM spend + outbound fetch
        ("bebshax.api.datasets.generate_personas_from_dataset", "10 per 1 minute"),
        ("bebshax.api.datasets.refresh_dataset", "10 per 1 hour"),
        ("bebshax.api.datasets.refresh_study_dataset", "10 per 1 hour"),
        # study creation is budgeted per signed-in account (fallback: client key)
        ("bebshax.api.studies.create_study", "60 per 1 hour"),
    ],
)
def test_llm_spending_routes_carry_rate_limits(qualified: str, expected: str):
    assert expected in _limit_str(qualified)


def test_study_creation_limit_is_keyed_per_account():
    from starlette.requests import Request

    from bebshax.api.studies import _account_or_client_key

    def _req(headers: dict[str, str]) -> Request:
        raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
        return Request({
            "type": "http", "method": "POST", "path": "/api/studies",
            "headers": raw, "client": ("198.51.100.4", 4242),
        })

    # No or unverifiable credentials fall back to the client key, never a shared bucket.
    assert _account_or_client_key(_req({})) == "198.51.100.4"
    assert _account_or_client_key(_req({"Authorization": "Bearer not-a-real-token"})) == "198.51.100.4"
    good = create_access_token({"sub": "usr_x"})
    assert _account_or_client_key(_req({"Authorization": f"Bearer {good}"})) == "account:usr_x"
    other = create_access_token({"sub": "usr_y"})
    assert _account_or_client_key(_req({"Authorization": f"Bearer {other}"})) == "account:usr_y"


# ---------------------------------------------------------------------------
# Per-user running-job cap
# ---------------------------------------------------------------------------

@pytest.fixture
async def jobs_cap_app(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'jobs_cap.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        session.add_all(
            [
                Users(
                    id="usr_cap", email="cap@example.com", hashed_password="x", full_name="Cap",
                    is_active=True, is_verified=True,
                ),
                Users(
                    id="usr_other_cap", email="other-cap@example.com", hashed_password="x",
                    full_name="Other", is_active=True, is_verified=True,
                ),
                Studies(id="std_cap", user_id="usr_cap", title="Cap Study", status="in_progress"),
                Studies(id="std_other_cap", user_id="usr_other_cap", title="Other", status="in_progress"),
            ]
        )
        await session.commit()

    from bebshax.main import create_app

    app = create_app()
    app.state.db_sessionmaker = maker
    yield app
    await engine.dispose()


def _headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': user_id})}"}


@pytest.mark.asyncio
async def test_fourth_concurrent_job_for_the_same_user_is_429(jobs_cap_app, monkeypatch):
    release = asyncio.Event()

    class BlockingService:
        def __init__(self, session, llm_service=None, *, ml_generator=None):
            assert ml_generator is not None

        async def create_generation_run(self, *, study_id, user_id, **_):
            await release.wait()
            run = PersonaGenerationRuns(
                id=f"pgen_{asyncio.get_running_loop().time():.0f}", study_id=study_id,
                user_id=user_id, status="completed", target_count=0, generated_count=0,
                valid_count=0, warning_count=0,
            )
            return run, []

    from bebshax.api import personas as personas_api

    monkeypatch.setattr(personas_api, "PersonaGenerationService", BlockingService)
    limiter._limiter.storage.reset()

    url = "/api/studies/std_cap/personas/generate/jobs"
    async with AsyncClient(transport=ASGITransport(app=jobs_cap_app), base_url="http://test") as client:
        job_ids = []
        for _ in range(3):
            res = await client.post(url, json={}, headers=_headers("usr_cap"))
            assert res.status_code == 202, res.text
            job_ids.append(res.json()["job_id"])

        blocked = await client.post(url, json={}, headers=_headers("usr_cap"))
        assert blocked.status_code == 429, blocked.text
        body = blocked.json()
        assert body["error_code"] == "too_many_jobs"
        assert body["max_running_jobs"] == 3
        assert "request_id" in body

        # The cap is per user: another tenant is unaffected.
        other = await client.post(
            "/api/studies/std_other_cap/personas/generate/jobs", json={}, headers=_headers("usr_other_cap")
        )
        assert other.status_code == 202, other.text

        release.set()
        for job_id in job_ids:
            for _ in range(200):
                job = (await client.get(f"{url}/{job_id}", headers=_headers("usr_cap"))).json()
                if job["status"] != "running":
                    break
                await asyncio.sleep(0.01)
            assert job["status"] == "completed"

        # Slots free up once jobs finish.
        again = await client.post(url, json={}, headers=_headers("usr_cap"))
        assert again.status_code == 202, again.text
    limiter._limiter.storage.reset()


# ---------------------------------------------------------------------------
# Request bounds
# ---------------------------------------------------------------------------

async def test_requested_count_above_50_is_422(api_test_app: TestClient, auth_headers):
    resp = api_test_app.post(
        "/api/datasets/ds_any/generate-personas",
        json={"requested_count": 51},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "validation_error"
    assert "requested_count" in resp.json()["message"]


async def test_requested_count_of_zero_is_422(api_test_app: TestClient, auth_headers):
    resp = api_test_app.post(
        "/api/datasets/ds_any/generate-personas", json={"requested_count": 0}, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "t" * 257, "prompt": "ok"},
        {"prompt": "ok", "type": "x" * 65},
        {"prompt": "ok", "goal": "g" * 65},
        {"prompt": "ok", "status": "s" * 65},
        {"prompt": "ok", "duration_text": "d" * 129},
        {"prompt": "p" * 20_001},
        {"prompt": "ok", "target_audience": "a" * 20_001},
        {"prompt": "ok", "pricing_hypothesis": "h" * 20_001},
    ],
)
async def test_study_create_fields_are_bounded_to_column_widths(api_test_app: TestClient, auth_headers, payload):
    resp = api_test_app.post("/api/studies", json=payload, headers=auth_headers)
    assert resp.status_code == 422, resp.text


async def test_study_update_title_is_bounded(api_test_app: TestClient, auth_headers):
    created = api_test_app.post("/api/studies", json={"prompt": "bounded"}, headers=auth_headers)
    assert created.status_code == 201
    resp = api_test_app.patch(
        f"/api/studies/{created.json()['id']}", json={"title": "t" * 257}, headers=auth_headers
    )
    assert resp.status_code == 422


async def test_study_create_accepts_exact_limits(api_test_app: TestClient, auth_headers):
    resp = api_test_app.post(
        "/api/studies",
        json={"title": "t" * 256, "prompt": "ok", "type": "x" * 64, "duration_text": "d" * 128},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text


async def test_copilot_roles_capped_at_ten(api_test_app: TestClient, auth_headers):
    roles = [
        {"id": f"role_{i}", "role": f"Role {i}", "description": "d", "count": 1, "selected": True}
        for i in range(11)
    ]
    resp = api_test_app.post(
        "/api/study/generate-personas",
        json={"study_prompt": "x", "roles": roles},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "roles" in resp.json()["message"]


async def test_copilot_messages_are_bounded(api_test_app: TestClient, auth_headers):
    too_long = {"messages": [{"role": "user", "content": "c" * 8001}]}
    assert api_test_app.post("/api/study/copilot", json=too_long, headers=auth_headers).status_code == 422

    too_many = {"messages": [{"role": "user", "content": "hi"}] * 61}
    assert api_test_app.post("/api/study/copilot", json=too_many, headers=auth_headers).status_code == 422
