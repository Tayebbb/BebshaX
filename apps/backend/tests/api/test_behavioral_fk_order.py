"""POST /studies/{id}/behavioral-tests was dead on Postgres.

The route staged the test row and its first scenario in ONE flush. No
``relationship()`` links the two mappers, so SQLAlchemy's unit of work ordered
the INSERTs alphabetically — ``BehavioralTestScenarios`` before
``BehavioralTests`` — and Postgres refused the child's FK (mapped to a 409).
sqlite never caught it because it ignores FOREIGN KEY constraints unless
``PRAGMA foreign_keys=ON`` runs on each connection; this module turns that on
for every engine BEFORE the app is built, so the same violation reproduces
here (red without the ``session.flush()`` in the route, green with it).
"""

import uuid

import pytest
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from starlette.testclient import TestClient

from bebshax.behavioral.orm import BehavioralTests, BehavioralTestScenarios


def _enable_sqlite_fk(dbapi_conn, _record) -> None:
    # Fires for every Engine (class-level listener); only sqlite needs the
    # pragma. aiosqlite's DBAPI adapter lives in
    # sqlalchemy.dialects.sqlite.aiosqlite and exposes a sync-style cursor.
    if "sqlite" not in type(dbapi_conn).__module__:
        return
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
def sqlite_fk_enforced():
    event.listen(Engine, "connect", _enable_sqlite_fk)
    try:
        yield
    finally:
        event.remove(Engine, "connect", _enable_sqlite_fk)


@pytest.fixture
async def fk_api_app(sqlite_fk_enforced, api_test_app):
    """Ordering matters: the listener must exist before create_app() opens
    the app's engine, so it is requested BEFORE the shared app fixture."""
    return api_test_app


async def _assert_fk_enforcement_is_live(app) -> None:
    """Precondition: without this the regression test could pass for the
    wrong reason (a scenario pointing at a missing test must be rejected)."""
    maker = app.state.db_sessionmaker
    async with maker() as session:
        session.add(
            BehavioralTestScenarios(
                id=f"bts_orphan_{uuid.uuid4().hex[:8]}",
                behavioral_test_id="bt_does_not_exist",
                title="orphan",
                scenario_text="points at no parent",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


def _create_study(client: TestClient, headers: dict[str, str]) -> str:
    created = client.post(
        "/api/studies",
        json={"prompt": "A dog-walking app for busy professionals in Berlin", "type": "interviews"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def test_create_behavioral_test_persists_parent_before_scenario(fk_api_app: TestClient, auth_headers):
    await _assert_fk_enforcement_is_live(fk_api_app.app)
    study_id = _create_study(fk_api_app, auth_headers)

    res = fk_api_app.post(
        f"/api/studies/{study_id}/behavioral-tests",
        json={
            "name": "Price sensitivity",
            "test_type": "pricing_test",
            "scenario_text": "A 30-minute walk costs 18 EUR, booked through the app the evening before.",
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["study_id"] == study_id and body["test_type"] == "pricing_test"
    assert [s["scenario_text"] for s in body["scenarios"]] == [
        "A 30-minute walk costs 18 EUR, booked through the app the evening before."
    ]

    # Both rows really are in the database (not just echoed from memory).
    detail = fk_api_app.get(f"/api/studies/{study_id}/behavioral-tests/{body['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert len(detail.json()["scenarios"]) == 1
    async with fk_api_app.app.state.db_sessionmaker() as session:
        rows = (
            await session.execute(
                select(BehavioralTestScenarios).where(BehavioralTestScenarios.behavioral_test_id == body["id"])
            )
        ).scalars().all()
        assert len(rows) == 1 and rows[0].scenario_text.startswith("A 30-minute walk")


async def test_empty_scenario_is_refused_before_any_row_is_staged(fk_api_app: TestClient, auth_headers):
    study_id = _create_study(fk_api_app, auth_headers)

    res = fk_api_app.post(
        f"/api/studies/{study_id}/behavioral-tests",
        json={"name": "No scenario", "test_type": "concept_test", "scenario_text": "   "},
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert res.json()["error_code"] == "scenario_required"

    async with fk_api_app.app.state.db_sessionmaker() as session:
        tests = (await session.execute(select(BehavioralTests).where(BehavioralTests.study_id == study_id))).scalars().all()
    assert tests == []
