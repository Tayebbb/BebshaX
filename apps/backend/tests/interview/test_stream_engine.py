"""Engine ask_stream parity with ask(), and the SSE endpoint."""

import json

from sqlalchemy import select

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.interview.orm import ConversationTurns

_SSE_OWNER_ID = "usr_sse_owner"
# Posting an interview message writes turns, so it needs the owner's token.
_SSE_HEADERS = {"Authorization": f"Bearer {create_access_token({'sub': _SSE_OWNER_ID})}"}


async def _seed_owner(session) -> None:
    session.add(
        Users(
            id=_SSE_OWNER_ID,
            email="sse-owner@example.com",
            full_name="SSE Owner",
            hashed_password="hash",
            is_active=True,
            is_verified=True,
        )
    )


async def _collect(agen):
    events = []
    async for e in agen:
        events.append(e)
    return events


async def test_ask_stream_persists_same_shape_as_ask(
    session_maker, stored_persona, memory_service, llm_factory
) -> None:
    from bebshax.interview.engine import InterviewEngine

    llm, _ = llm_factory(["I buy lunch near campus most days."])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "spend check")

    events = await _collect(engine.ask_stream(conversation.id, "Where do you eat lunch?"))
    assert events[0]["type"] == "delta"
    done = events[-1]
    assert done["type"] == "done"
    assert done["reply"] == "I buy lunch near campus most days."
    assert done["turn_number"] == 2
    assert done["served_by"] == "fake/m1"
    for key in ("topics_explored", "suggested_questions", "decision_state", "max_turns"):
        assert key in done

    async with session_maker() as session:
        turns = list(
            (
                await session.execute(
                    select(ConversationTurns).order_by(ConversationTurns.turn_number)
                )
            ).scalars()
        )
    assert [t.role for t in turns] == ["interviewer", "persona"]
    assert turns[1].content == "I buy lunch near campus most days."
    assert turns[1].served_by == "fake/m1"


async def test_ask_stream_over_pool_router_releases_slot_and_fires_provenance(
    session_maker, stored_persona, memory_service
) -> None:
    """Regression (critic #1): ask_stream breaks out of the router generator —
    the pool slot and provenance must settle immediately, not at GC."""
    from bebshax.interview.engine import InterviewEngine
    from bebshax.llm.adapters.base import RouteCandidate
    from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
    from bebshax.llm.router import PoolRouter

    records = []
    fake = FakeAdapter(
        [FakeRoute(candidate=RouteCandidate(provider="fake", model="m1"), reply="On the router.")]
    )
    router = PoolRouter(
        {"openrouter": fake, "freellmpool": fake, "ollama": fake},
        on_provenance=records.append,
    )
    engine = InterviewEngine(router, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "router stream check")

    events = await _collect(engine.ask_stream(conversation.id, "Say something."))
    assert events[-1]["type"] == "done"
    assert events[-1]["reply"] == "On the router."
    assert router.pool_utilization()["conversation"]["active_requests"] == 0
    assert records and records[0].success is True
    assert records[0].served_by_model == "m1"
    # Successful attempts must not be stamped "aborted by consumer".
    assert records[0].attempts[-1].failure_detail is None


async def test_sse_endpoint_emits_error_event_with_kind(
    session_maker, stored_persona, memory_service
) -> None:
    """A no-route failure must arrive as a typed SSE error event, not a crash."""
    from httpx import ASGITransport, AsyncClient

    from bebshax.db.models import Studies
    from bebshax.interview.engine import InterviewEngine
    from bebshax.llm.adapters.base import RouteCandidate
    from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
    from bebshax.llm.failures import FailureKind
    from bebshax.llm.router import PoolRouter
    from bebshax.main import app

    dead = FakeAdapter(
        [
            FakeRoute(
                candidate=RouteCandidate(provider="fake", model="dead"),
                behaviors=[FailureKind.SERVER_ERROR] * 4,
            )
        ]
    )
    router = PoolRouter({"openrouter": dead, "freellmpool": dead, "ollama": dead})
    engine = InterviewEngine(router, session_maker, memory=memory_service)

    saved = {
        n: getattr(app.state, n, None)
        for n in ("db_sessionmaker", "interview_engine", "llm_router", "llm_service")
    }
    app.state.db_sessionmaker = session_maker
    app.state.interview_engine = engine
    app.state.llm_router = router
    app.state.llm_service = router

    try:
        async with session_maker() as session:
            await _seed_owner(session)
            session.add(
                Studies(
                    id="std_sse_err",
                    user_id=_SSE_OWNER_ID,
                    title="SSE Err",
                    status="in_progress",
                )
            )
            await session.commit()
        conversation = await engine.start(
            stored_persona.id, "err check", study_id="std_sse_err", user_id=_SSE_OWNER_ID
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream(
                "POST",
                f"/api/studies/std_sse_err/interviews/{conversation.id}/messages/stream",
                json={"content": "Anyone there?"},
                headers=_SSE_HEADERS,
            ) as resp:
                raw = (await resp.aread()).decode()

        assert "event: error" in raw
        assert '"kind": "no_route"' in raw
    finally:
        for n, v in saved.items():
            if v is None:
                if hasattr(app.state, n):
                    delattr(app.state, n)
            else:
                setattr(app.state, n, v)


async def test_sse_endpoint_emits_delta_then_done(
    session_maker, stored_persona, memory_service, llm_factory
) -> None:
    from httpx import ASGITransport, AsyncClient

    from bebshax.db.models import Studies
    from bebshax.interview.engine import InterviewEngine
    from bebshax.main import app

    llm, _ = llm_factory(["Streaming reply."])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)

    saved = {
        n: getattr(app.state, n, None)
        for n in ("db_sessionmaker", "interview_engine", "llm_router", "llm_service")
    }
    app.state.db_sessionmaker = session_maker
    app.state.interview_engine = engine
    app.state.llm_router = llm
    app.state.llm_service = llm

    try:
        async with session_maker() as session:
            await _seed_owner(session)
            session.add(
                Studies(
                    id="std_sse",
                    user_id=_SSE_OWNER_ID,
                    title="SSE Study",
                    status="in_progress",
                )
            )
            await session.commit()

        conversation = await engine.start(
            stored_persona.id, "sse check", study_id="std_sse", user_id=_SSE_OWNER_ID
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream(
                "POST",
                f"/api/studies/std_sse/interviews/{conversation.id}/messages/stream",
                json={"content": "Say something."},
                headers=_SSE_HEADERS,
            ) as resp:
                assert resp.status_code == 200
                assert resp.headers["content-type"].startswith("text/event-stream")
                raw = (await resp.aread()).decode()

        assert "event: delta" in raw
        assert "event: done" in raw
        done_json = json.loads(
            [ln for ln in raw.splitlines() if ln.startswith("data: ")][-1][len("data: "):]
        )
        assert done_json["reply"] == "Streaming reply."
        assert done_json["served_by"] == "fake/m1"
    finally:
        for n, v in saved.items():
            if v is None:
                if hasattr(app.state, n):
                    delattr(app.state, n)
            else:
                setattr(app.state, n, v)
