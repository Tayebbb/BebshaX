"""Integration tests for all REST API endpoints (Phase 13).

The shared `api_test_app` fixture lives in tests/conftest.py.
"""

from starlette.testclient import TestClient

from bebshax.llm.adapters.fake import FakeAdapter


async def test_routes_status_and_provenance(api_test_app: TestClient):
    # Test routes status
    status_resp = api_test_app.get("/api/routes/status")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert "providers" in data
    assert "pools" in data
    assert len(data["providers"]) >= 1

    # M2: types come from the registry table, never substring guessing —
    # the fixture's "pollinations" adapter has no registry entry.
    by_name = {p["name"]: p for p in data["providers"]}
    assert by_name["pollinations"]["type"] == "unknown"
    assert by_name["ollama"]["type"] == "local"
    # M2: active_requests is a real measured integer while the system is idle
    assert all(p["active_requests"] == 0 for p in data["pools"])

    # Test provenance list
    prov_resp = api_test_app.get("/api/provenance?limit=10")
    assert prov_resp.status_code == 200
    pdata = prov_resp.json()
    assert "items" in pdata
    assert "total" in pdata


async def test_routes_status_reports_empty_pools_honestly(api_test_app: TestClient):
    # M2: an empty pool must report 0 candidates — the audited code did max(count, 1)
    app = api_test_app.app
    saved = app.state.llm_adapters
    app.state.llm_adapters = {name: FakeAdapter(routes=[]) for name in saved}
    try:
        data = api_test_app.get("/api/routes/status").json()
        assert all(p["candidates_count"] == 0 for p in data["pools"])
        assert all(p["status"] == "degraded" for p in data["providers"])
    finally:
        app.state.llm_adapters = saved


async def test_evaluation_metrics_endpoint(api_test_app: TestClient):
    res = api_test_app.get("/api/evaluation/metrics")
    assert res.status_code == 200
    metrics = res.json()
    assert "overall_health" in metrics
    assert "routing_strategies" in metrics
    assert len(metrics["routing_strategies"]) == 4


async def test_business_and_persona_and_interview_e2e(api_test_app: TestClient):
    # 1. Create Business
    b_res = api_test_app.post(
        "/api/businesses",
        json={
            "name": "SwiftCourier App",
            "description": "Instant gig earnings management",
            "industry": "Gig Economy",
            "target_market": "Couriers",
        },
    )
    assert b_res.status_code == 201
    biz = b_res.json()
    biz_id = biz["id"]

    # 2. List Businesses
    blist_res = api_test_app.get("/api/businesses")
    assert blist_res.status_code == 200
    assert any(b["id"] == biz_id for b in blist_res.json())

    # 3. Generate Persona
    p_gen = api_test_app.post(
        f"/api/businesses/{biz_id}/personas",
        json={
            "audience_segment": "High-mileage courier",
            "generation_hints": ["Prioritize vehicle maintenance costs"],
        },
    )
    assert p_gen.status_code == 201
    persona = p_gen.json()
    persona_id = persona["id"]
    assert persona["name"] == "Alex Mercer"

    # 4. List Personas
    plist_res = api_test_app.get("/api/personas")
    assert plist_res.status_code == 200
    assert len(plist_res.json()) >= 1

    # 5. Get Single Persona
    p_get = api_test_app.get(f"/api/personas/{persona_id}")
    assert p_get.status_code == 200
    assert p_get.json()["id"] == persona_id

    # 6. Check Persona Memories
    mem_res = api_test_app.get(f"/api/personas/{persona_id}/memories")
    assert mem_res.status_code == 200
    memories = mem_res.json()
    assert isinstance(memories, list)

    # 7. Start Conversation
    c_res = api_test_app.post(
        "/api/conversations",
        json={"persona_id": persona_id, "objective": "Test new savings feature"},
    )
    assert c_res.status_code == 201
    conv_id = c_res.json()["id"]

    # 8. Post message
    msg_res = api_test_app.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Would you use an automated 5% buffer deduction?"},
    )
    assert msg_res.status_code == 200
    msg_data = msg_res.json()
    assert "Alex" in msg_data["reply"]
    assert msg_data["user_message"]["content"] == "Would you use an automated 5% buffer deduction?"
    # M4: latency/route/memories must be REAL values from the engine — the
    # audited code hardcoded latency_ms=750 and invented placeholder memories.
    reply_meta = msg_data["persona_reply"]
    assert isinstance(reply_meta["latency_ms"], (int, float)) and reply_meta["latency_ms"] > 0
    assert reply_meta["latency_ms"] != 750  # the audit's fabricated constant
    assert reply_meta["served_by"] == "pollinations/deepseek-r1"  # the FakeRoute actually serving
    assert any("Alex Mercer" in m for m in reply_meta["retrieved_memories"]), (
        "retrieved_memories must be the actual memory texts used in composition"
    )
    assert "Alex" in msg_data["persona_reply"]["content"]

    # 9. Get transcript
    tr_res = api_test_app.get(f"/api/conversations/{conv_id}")
    assert tr_res.status_code == 200
    turns = tr_res.json()["turns"]
    assert len(turns) == 2


async def test_memories_for_unknown_persona_is_404(api_test_app: TestClient):
    # M9: nonexistent persona must not masquerade as "no memories yet"
    resp = api_test_app.get("/api/personas/per_does_not_exist/memories")
    assert resp.status_code == 404


async def test_memories_without_service_is_503(api_test_app: TestClient):
    # M9: a missing memory service is an operational condition, not an empty list
    app = api_test_app.app
    saved = app.state.memory_service
    app.state.memory_service = None
    try:
        resp = api_test_app.get("/api/personas/anything/memories")
        assert resp.status_code == 503
    finally:
        app.state.memory_service = saved


async def test_user_studies_persistence_and_isolation(api_test_app: TestClient):
    # 1. Create study for User A (unauthenticated — user_id in body)
    s1_resp = api_test_app.post(
        "/api/studies",
        json={
            "user_id": "usr_alice",
            "title": "Alice's Grocery Delivery Demand Study",
            "type": "interviews",
            "goal": "demand_validation",
            "persona_count": 2,
            "copilot_messages": [{"role": "user", "content": "grocery delivery idea"}],
            "personas_data": [{"id": "per_1", "name": "Alice Persona"}],
        },
    )
    assert s1_resp.status_code == 201
    s1 = s1_resp.json()
    assert s1["user_id"] == "usr_alice"
    assert s1["title"] == "Alice's Grocery Delivery Demand Study"
    # Verify new fields are returned in the response
    assert s1["copilot_messages"] == [{"role": "user", "content": "grocery delivery idea"}]
    assert s1["personas_data"] == [{"id": "per_1", "name": "Alice Persona"}]

    # 2. Create study for User B
    s2_resp = api_test_app.post(
        "/api/studies",
        json={
            "user_id": "usr_bob",
            "title": "Bob's Fintech Card Study",
            "type": "concept_test",
            "goal": "feature_feedback",
            "persona_count": 3,
        },
    )
    assert s2_resp.status_code == 201
    s2 = s2_resp.json()
    assert s2["user_id"] == "usr_bob"

    # 3. List studies filtered by User A — only Alice's study (no auth JWT used)
    alice_studies = api_test_app.get("/api/studies?user_id=usr_alice").json()
    assert any(s["id"] == s1["id"] for s in alice_studies)
    assert not any(s["id"] == s2["id"] for s in alice_studies)

    # 4. List studies filtered by User B
    bob_studies = api_test_app.get("/api/studies?user_id=usr_bob").json()
    assert any(s["id"] == s2["id"] for s in bob_studies)
    assert not any(s["id"] == s1["id"] for s in bob_studies)

    # 5. Unauthenticated GET /api/studies (no user_id) returns only demo studies (empty here)
    unauth_studies = api_test_app.get("/api/studies").json()
    assert not any(s["id"] in (s1["id"], s2["id"]) for s in unauth_studies)

    # 6. Update study — no JWT so current_user=None; study.user_id="usr_alice" → owner check
    #    With no JWT the ownership guard sees current_user=None and study is not demo → 403
    patch_resp = api_test_app.patch(
        f"/api/studies/{s1['id']}",
        json={"status": "in_progress", "step": 3, "user_id": "usr_alice"},
    )
    # update_study auto-backfills user_id when study.user_id is already set; with no JWT
    # current_user=None so _user_owns_study → False → 403
    assert patch_resp.status_code == 403

    # 7. Update succeeds when user_id matches via the study auto-create path (new study_id)
    patch2_resp = api_test_app.patch(
        f"/api/studies/new_study_xyz",
        json={"status": "in_progress", "step": 2, "user_id": "usr_alice", "title": "New auto-created"},
    )
    assert patch2_resp.status_code == 200
    assert patch2_resp.json()["step"] == 2

    # 8. Delete study — same ownership rule applies
    del_resp = api_test_app.delete(f"/api/studies/{s2['id']}")
    assert del_resp.status_code == 403

    # 9. Cleanup: delete studies via same user_id trick (auto-create path gives owner access)
    #    Just verify that the created studies still exist (delete was blocked)
    check = api_test_app.get(f"/api/studies?user_id=usr_bob").json()
    assert any(s["id"] == s2["id"] for s in check)

