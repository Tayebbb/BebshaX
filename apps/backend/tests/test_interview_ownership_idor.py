"""IDOR & Multi-tenant Isolation Tests for Adaptive Persona Interviews (Part 6).

Verifies that:
- User A (Study A, Persona A, Interview A) cannot access User B's (Study B, Persona B, Interview B) interviews.
- Attempting to list, read, post messages to, complete, or fetch insights for User B's interview returns 403 Forbidden.
- Attempting to start an interview on Persona B under Study A is rejected.
"""

import pytest
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
        user_a = Users(id="usr_a", email="usera@example.com", hashed_password="hashed_pw_a", full_name="User A")
        study_a = Studies(id="std_a", user_id="usr_a", title="Study A", status="in_progress")
        persona_a = Personas(id="per_a", study_id="std_a", user_id="usr_a", owner_id="usr_a", name="Persona A", version=1)
        conv_a = Conversations(id="conv_a", study_id="std_a", user_id="usr_a", persona_id="per_a", objective="Obj A", status="active")
        ins_a = InterviewInsights(id="ins_a", interview_id="conv_a", study_id="std_a", user_id="usr_a", persona_id="per_a", type="pain_point", title="Insight A", description="Desc A")

        # User B setup
        user_b = Users(id="usr_b", email="userb@example.com", hashed_password="hashed_pw_b", full_name="User B")
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

        # 1. User A listing User B's study interviews -> 404 or 403
        res = await client.get("/api/studies/std_b/interviews", headers=headers_a)
        assert res.status_code in (403, 404)

        # 2. User B listing User B's study interviews -> 200
        res_ok = await client.get("/api/studies/std_b/interviews", headers=headers_b)
        assert res_ok.status_code == 200
        assert res_ok.json()["total"] == 1

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


