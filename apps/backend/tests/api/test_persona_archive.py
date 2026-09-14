"""Removing a persona from the study panel must persist and keep its history.

Live 2026-09-14 (sweep B, D7): "Remove persona" showed (4) then a PATCH of
``personas_data`` was accepted with 200 but ignored as server-derived; reload
showed the persona again. The panel is now edited through a real endpoint that
archives the row, refreshes the derived study state and bumps the revision.
"""

from sqlalchemy import select
from starlette.testclient import TestClient

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Personas, Studies
from bebshax.interview.orm import Conversations, ConversationTurns

_OWNER = "usr_archive_owner"
_OTHER = "usr_archive_other"


def _headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': user_id})}"}


async def _seed(app) -> None:
    async with app.state.db_sessionmaker() as session:
        for user_id, email in ((_OWNER, "archive-owner@example.com"), (_OTHER, "archive-other@example.com")):
            if await session.get(Users, user_id) is None:
                session.add(Users(id=user_id, email=email, full_name="A", hashed_password="x", is_active=True, is_verified=True))
        session.add(Studies(id="std_arch", user_id=_OWNER, title="Archive", status="in_progress", persona_count=2,
                            persona_ids=["per_a", "per_b"], personas_data=[{"id": "per_a"}, {"id": "per_b"}]))
        await session.flush()
        session.add_all([
            Personas(id="per_a", study_id="std_arch", user_id=_OWNER, owner_id=_OWNER, name="Ana", version=1, status="active"),
            Personas(id="per_b", study_id="std_arch", user_id=_OWNER, owner_id=_OWNER, name="Bo", version=1, status="active"),
        ])
        await session.flush()
        session.add(Conversations(id="conv_a", study_id="std_arch", persona_id="per_a", objective="o", user_id=_OWNER, status="completed", turn_count=1))
        await session.flush()
        session.add(ConversationTurns(id="turn_a", conversation_id="conv_a", turn_number=1, role="persona", content="kept"))
        await session.commit()


async def test_archiving_a_persona_persists_and_keeps_its_interview(api_test_app: TestClient):
    app = api_test_app.app
    await _seed(app)
    before = api_test_app.get("/api/studies/std_arch", headers=_headers(_OWNER)).json()
    assert before["persona_count"] == 2

    resp = api_test_app.delete("/api/studies/std_arch/personas/per_a", headers=_headers(_OWNER))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["persona_ids"] == ["per_b"] and body["persona_count"] == 1
    assert body["study_revision"] > before["revision"]

    after = api_test_app.get("/api/studies/std_arch", headers=_headers(_OWNER)).json()
    assert after["persona_ids"] == ["per_b"] and after["revision"] == body["study_revision"]
    listed = api_test_app.get("/api/studies/std_arch/personas", headers=_headers(_OWNER)).json()
    assert [persona["id"] for persona in listed["personas"]] == ["per_b"]

    async with app.state.db_sessionmaker() as session:
        archived = await session.get(Personas, "per_a")
        assert archived is not None and archived.status == "archived"
        assert await session.get(Conversations, "conv_a") is not None
        assert await session.get(ConversationTurns, "turn_a") is not None

    # Idempotence: a second removal reports not-found instead of touching the row again.
    assert api_test_app.delete("/api/studies/std_arch/personas/per_a", headers=_headers(_OWNER)).status_code == 404


async def test_archiving_requires_the_study_owner(api_test_app: TestClient):
    app = api_test_app.app
    await _seed(app)
    resp = api_test_app.delete("/api/studies/std_arch/personas/per_b", headers=_headers(_OTHER))
    assert resp.status_code in (403, 404), resp.text
    async with app.state.db_sessionmaker() as session:
        row = (await session.execute(select(Personas).where(Personas.id == "per_b"))).scalar_one()
        assert row.status == "active"
    assert api_test_app.delete("/api/studies/std_arch/personas/per_b").status_code == 401
