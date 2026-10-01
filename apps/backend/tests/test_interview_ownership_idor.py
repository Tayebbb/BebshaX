"""IDOR & Multi-tenant Isolation Tests for Adaptive Persona Interviews (Part 6).

Verifies that:
- User A (Study A, Persona A, Interview A) cannot access User B's (Study B, Persona B, Interview B) interviews.
- Attempting to list, read, post messages to, complete, or fetch insights for User B's interview returns 403 Forbidden.
- Attempting to start an interview on Persona B under Study A is rejected.
"""

import pytest
from datetime import datetime, timedelta, timezone
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.config import get_settings
from bebshax.db.models import Base, Personas, Studies
from bebshax.interview.engine import InterviewEngine
from bebshax.interview.orm import Conversations, ConversationTurns, InterviewInsights
from bebshax.llm import SingleAdapterLLMService
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute


@pytest.mark.asyncio
async def test_user_a_cannot_access_user_b_interviews(tmp_path, monkeypatch):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'idor_interview.db'}"
    monkeypatch.setenv("BEBSHAX_DATABASE_URL", db_url)
    get_settings.cache_clear()

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as session:
        # User A setup
        user_a = Users(id="usr_a", email="usera@example.com", hashed_password="hashed_pw_a", full_name="User A", is_verified=True)
        study_a = Studies(id="std_a", user_id="usr_a", title="Study A", status="in_progress")
        persona_a = Personas(id="per_a", study_id="std_a", user_id="usr_a", owner_id="usr_a", name="Persona A", version=1)
        conv_a = Conversations(id="conv_a", study_id="std_a", user_id="usr_a", persona_id="per_a", objective="Obj A", status="active")
        ins_a = InterviewInsights(id="ins_a", interview_id="conv_a", study_id="std_a", user_id="usr_a", persona_id="per_a", type="pain_point", title="Insight A", description="Desc A")

        # User B setup
        user_b = Users(id="usr_b", email="userb@example.com", hashed_password="hashed_pw_b", full_name="User B", is_verified=True)
        study_b = Studies(id="std_b", user_id="usr_b", title="Study B", status="in_progress")
        persona_b = Personas(id="per_b", study_id="std_b", user_id="usr_b", owner_id="usr_b", name="Persona B", version=1)
        conv_b = Conversations(id="conv_b", study_id="std_b", user_id="usr_b", persona_id="per_b", objective="Obj B", status="active")
        ins_b = InterviewInsights(id="ins_b", interview_id="conv_b", study_id="std_b", user_id="usr_b", persona_id="per_b", type="pricing", title="Insight B", description="Desc B")

        session.add_all([user_a, study_a, persona_a, conv_a, ins_a, user_b, study_b, persona_b, conv_b, ins_b])
        await session.commit()
    await engine.dispose()

    from bebshax.main import create_app
    app = create_app()

    token_a = create_access_token({"sub": "usr_a", "email": "usera@example.com"})
    token_b = create_access_token({"sub": "usr_b", "email": "userb@example.com"})

    adapter = FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="fake", model="m1"), replies=["Hello!"])])
    llm = SingleAdapterLLMService(adapter)
    app.state.db_sessionmaker = maker
    app.state.interview_engine = InterviewEngine(
        llm, maker, memory=getattr(app.state, "memory_service", None)
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 1. User A listing User B's study interviews -> 404: a 403 here confirmed
        # the study existed while /studies/{id} and /personas said 404 (live 2026-09-14).
        res = await client.get("/api/studies/std_b/interviews", headers=headers_a)
        assert res.status_code == 404
        assert res.json()["detail"] == "Study not found"

        # 2. User B listing User B's study interviews -> 200
        res_ok = await client.get("/api/studies/std_b/interviews", headers=headers_b)
        assert res_ok.status_code == 200
        assert res_ok.json()["total"] == 1

        # 2b. Search covers the explored topics printed on every card
        # (live 2026-09-14: "pricing" matched nothing although pricing_budget was explored).
        async with maker() as session:
            row = await session.get(Conversations, "conv_b")
            row.topics_explored = {"pricing_budget": "explored", "current_alternatives": "explored"}
            await session.commit()
        for term, expected in (("pricing", 1), ("current alternatives", 1), ("persona b", 1), ("objections", 0)):
            res_search = await client.get("/api/studies/std_b/interviews", params={"search": term}, headers=headers_b)
            assert res_search.status_code == 200
            assert res_search.json()["total"] == expected, term

        # 3. User A getting metrics for User B's study -> 404 or 403
        res_m = await client.get("/api/studies/std_b/interviews/metrics", headers=headers_a)
        assert res_m.status_code in (403, 404)

        # 4. User A getting detail of User B's interview -> 404 or 403
        res_det = await client.get("/api/studies/std_b/interviews/conv_b", headers=headers_a)
        assert res_det.status_code in (403, 404)

        # 5. User A trying to access User B's interview by tampering study_id (std_a/conv_b) -> 403 or 404
        res_tamper = await client.get("/api/studies/std_a/interviews/conv_b", headers=headers_a)
        assert res_tamper.status_code in (403, 404)

        # 6. User A posting message to User B's interview -> 404 or 403
        res_msg = await client.post(
            "/api/studies/std_b/interviews/conv_b/messages",
            json={"content": "Malicious probe"},
            headers=headers_a,
        )
        assert res_msg.status_code in (403, 404)

        # 7. User A completing User B's interview -> 404 or 403
        res_comp = await client.post(
            "/api/studies/std_b/interviews/conv_b/complete",
            headers=headers_a,
        )
        assert res_comp.status_code in (403, 404)

        # 8. User A fetching User B's interview insights -> 404 or 403
        res_ins = await client.get(
            "/api/studies/std_b/interviews/conv_b/insights",
            headers=headers_a,
        )
        assert res_ins.status_code in (403, 404)

        # 9. User A trying to start interview with User B's persona under User A's study -> 403 or 404
        res_start_foreign = await client.post(
            "/api/studies/std_a/personas/per_b/interviews",
            json={"objective": "Test"},
            headers=headers_a,
        )
        assert res_start_foreign.status_code in (403, 404)


@pytest.mark.asyncio
async def test_study_interview_list_pages_newest_first_and_counts_every_match(tmp_path, monkeypatch):
    """The list used to return every interview of a study; it now serves one
    bounded page while ``total`` still counts everything the filters matched."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'interview_pages.db'}"
    monkeypatch.setenv("BEBSHAX_DATABASE_URL", db_url)
    get_settings.cache_clear()

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    base = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    async with maker() as session:
        session.add_all([
            Users(id="usr_p", email="pages@example.com", hashed_password="pw", full_name="Pages", is_verified=True),
            Studies(id="std_p", user_id="usr_p", title="Paged Study", status="in_progress"),
            Personas(id="per_p", study_id="std_p", user_id="usr_p", owner_id="usr_p", name="Paged Persona", version=1),
            *[
                Conversations(
                    id=f"conv_{i}", study_id="std_p", user_id="usr_p", persona_id="per_p", objective="Obj",
                    status="completed", created_at=base + timedelta(minutes=i),
                    topics_explored={"pricing_budget": "explored"} if i % 2 else {},
                )
                for i in range(3)
            ],
        ])
        await session.commit()
    await engine.dispose()

    from bebshax.main import create_app
    app = create_app()
    app.state.db_sessionmaker = maker
    headers = {"Authorization": f"Bearer {create_access_token({'sub': 'usr_p', 'email': 'pages@example.com'})}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        everything = (await client.get("/api/studies/std_p/interviews", headers=headers)).json()
        assert everything["total"] == 3
        assert [item["id"] for item in everything["interviews"]] == ["conv_2", "conv_1", "conv_0"]

        first = (await client.get("/api/studies/std_p/interviews", params={"limit": 2}, headers=headers)).json()
        assert first["total"] == 3 and [item["id"] for item in first["interviews"]] == ["conv_2", "conv_1"]

        last = (await client.get("/api/studies/std_p/interviews", params={"limit": 2, "offset": 2}, headers=headers)).json()
        assert last["total"] == 3 and [item["id"] for item in last["interviews"]] == ["conv_0"]

        # The text search filters in Python; the page and the total still agree.
        searched = (await client.get(
            "/api/studies/std_p/interviews", params={"search": "pricing", "limit": 1}, headers=headers,
        )).json()
        assert searched["total"] == 1 and [item["id"] for item in searched["interviews"]] == ["conv_1"]

        for bad in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
            assert (await client.get("/api/studies/std_p/interviews", params=bad, headers=headers)).status_code == 422


@pytest.mark.asyncio
async def test_interview_metrics_aggregation_matches_counting(tmp_path, monkeypatch):
    """Fix-3 regression: SQL aggregation must return the same totals as the
    old Python list-counting approach for a known dataset."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'metrics_test.db'}"
    monkeypatch.setenv("BEBSHAX_DATABASE_URL", db_url)
    get_settings.cache_clear()

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as session:
        user = Users(id="usr_m", email="metrics@example.com", hashed_password="pw", full_name="Metrics", is_verified=True)
        study = Studies(id="std_m", user_id="usr_m", title="Metrics Study", status="in_progress")
        persona = Personas(id="per_m", study_id="std_m", user_id="usr_m", owner_id="usr_m", name="P", version=1)
        # 2 active, 3 completed, 1 other
        convs = [
            Conversations(id=f"cv_{i}", study_id="std_m", user_id="usr_m", persona_id="per_m",
                          objective="Test", status=st)
            for i, st in enumerate(["active", "active", "completed", "completed", "completed", "pending"])
        ]
        session.add_all([user, study, persona] + convs)
        await session.commit()
    await engine.dispose()

    from bebshax.main import create_app
    app = create_app()
    token = create_access_token({"sub": "usr_m", "email": "metrics@example.com"})

    adapter = FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="fake", model="m1"), replies=["Hi"])])
    llm = SingleAdapterLLMService(adapter)
    app.state.db_sessionmaker = maker
    app.state.interview_engine = InterviewEngine(llm, maker, memory=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/studies/std_m/interviews/metrics",
                               headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["total_interviews"] == 6
    assert data["active_interviews"] == 2
    assert data["completed_interviews"] == 3


@pytest.mark.asyncio
async def test_parentless_rows_are_rejected_not_silently_accepted(tmp_path, monkeypatch):
    """The study-scoping guards used to read ``if row.study_id and row.study_id != study_id``.

    A row whose ``study_id`` is NULL skipped the comparison entirely and was
    therefore accepted under ANY study id — read *and* write. These fixtures are
    exactly that shape.
    """
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'null_parent.db'}"
    monkeypatch.setenv("BEBSHAX_DATABASE_URL", db_url)
    get_settings.cache_clear()

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as session:
        session.add_all([
            Users(id="usr_np", email="np@example.com", hashed_password="pw", full_name="NP", is_verified=True),
            Studies(id="std_np", user_id="usr_np", title="Own Study", status="in_progress"),
            # Both children are parentless: study_id is NULL.
            Personas(id="per_np", study_id=None, user_id="usr_np", owner_id="usr_np",
                     name="Orphan Persona", version=1),
            Conversations(id="conv_np", study_id=None, user_id="usr_np", persona_id="per_np",
                          objective="Orphan", status="active"),
            # Positive control: correctly parented, same owner.
            Personas(id="per_ok", study_id="std_np", user_id="usr_np", owner_id="usr_np",
                     name="Parented Persona", version=1),
        ])
        await session.commit()
    await engine.dispose()

    from bebshax.main import create_app
    app = create_app()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': 'usr_np', 'email': 'np@example.com'})}"}

    adapter = FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="fake", model="m1"), replies=["Hi"])])
    app.state.db_sessionmaker = maker
    app.state.interview_engine = InterviewEngine(SingleAdapterLLMService(adapter), maker, memory=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Reads: the orphan must not surface under a study it has no link to.
        assert (await client.get("/api/studies/std_np/interviews/conv_np", headers=headers)).status_code == 403
        assert (await client.get("/api/studies/std_np/interviews/conv_np/insights", headers=headers)).status_code == 403
        # Writes: and it must certainly not be mutable through one.
        assert (await client.post(
            "/api/studies/std_np/interviews/conv_np/messages",
            json={"content": "probe"}, headers=headers,
        )).status_code == 403
        assert (await client.post(
            "/api/studies/std_np/interviews/conv_np/complete", headers=headers,
        )).status_code == 403
        assert (await client.post(
            "/api/studies/std_np/personas/per_np/interviews",
            json={"objective": "probe"}, headers=headers,
        )).status_code == 403

        # The owner's own, correctly parented persona still works end to end.
        start = await client.post(
            "/api/studies/std_np/personas/per_ok/interviews",
            json={"objective": "probe"}, headers=headers,
        )
        assert start.status_code == 201


