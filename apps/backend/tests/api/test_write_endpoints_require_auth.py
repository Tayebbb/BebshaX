"""Regression: every write endpoint (POST/DELETE) must return 401 when
unauthenticated, not 500 / crash / NULL owner_id insert.

Correction to B6 Stage 2 (commit 5a5500e) where write endpoints used
get_optional_current_user instead of get_current_user.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.db.models import Base
from bebshax.main import app

_engine = create_async_engine("sqlite+aiosqlite:///:memory:")


@pytest.fixture(scope="module", autouse=True)
def _setup_app_db():
    import asyncio

    async def init():
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init())
    sm = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    app.state.db_sessionmaker = sm
    app.state.sessionmaker = sm


client = TestClient(app)


# -------------------------------------------------------------------------
# Legacy endpoints (businesses / personas)
# -------------------------------------------------------------------------


def test_create_business_without_auth_returns_401():
    """POST /api/businesses must reject unauthenticated requests with 401,
    not crash on None user or silently assign to usr_system_holder."""
    response = client.post("/api/businesses", json={"name": "Should Not Be Created"})
    assert response.status_code == 401


def test_generate_persona_without_auth_returns_401():
    """POST /api/businesses/{id}/personas must reject unauthenticated requests."""
    response = client.post(
        "/api/businesses/some-nonexistent-id/personas",
        json={"hints": "test"},
    )
    assert response.status_code == 401


# -------------------------------------------------------------------------
# Study-scoped endpoints
# -------------------------------------------------------------------------


def test_study_generate_personas_without_auth_returns_401():
    """POST /api/studies/{id}/personas/generate must reject unauthenticated requests."""
    response = client.post(
        "/api/studies/std_fake/personas/generate",
        json={"segmentation_run_id": "run_x"},
    )
    assert response.status_code == 401


def test_study_regenerate_persona_without_auth_returns_401():
    """POST /api/studies/{id}/personas/{pid}/regenerate must reject unauthenticated requests."""
    response = client.post("/api/studies/std_fake/personas/per_fake/regenerate")
    assert response.status_code == 401


def test_study_delete_persona_run_without_auth_returns_401():
    """DELETE /api/studies/{id}/persona-runs/{rid} must reject unauthenticated requests."""
    response = client.delete("/api/studies/std_fake/persona-runs/run_fake")
    assert response.status_code == 401
