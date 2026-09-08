"""Tests for Market Segmentation multi-user authorization and IDOR protection.

Verifies that User B cannot view, trigger, compare, or delete User A's segmentation runs or segments,
and all unowned access returns 404 to avoid leaking existence or metadata.
"""

import io
import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.router import PoolRouter
from bebshax.main import app

_SEGMENTS_REPLY = json.dumps(
    {
        "segments": [
            {"cluster_label": "cluster_0", "name": "Lower-budget planners", "description": "Lower half of budgets.", "differentiation_summary": "Spend less."},
            {"cluster_label": "cluster_1", "name": "Higher-budget planners", "description": "Upper half of budgets.", "differentiation_summary": "Spend more."},
        ]
    }
)


def _fake_llm():
    fake = FakeAdapter(routes=[FakeRoute(candidate=RouteCandidate(provider="pollinations", model="deepseek-r1"), reply=_SEGMENTS_REPLY)])
    return PoolRouter({n: fake for n in ("openrouter", "freellmpool", "ollama", "pollinations")})


@pytest.mark.asyncio
async def test_segmentation_multi_user_idor_isolation():
    """Verify strict user-scoped segmentation access and IDOR protection."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_sessionmaker = session_maker
    app.state.llm_service = _fake_llm()

    # 1. Create User A and User B
    async with session_maker() as session:
        user_a = Users(id="usr_a_seg", email="usera_seg@example.com", full_name="User A", hashed_password="pw")
        user_b = Users(id="usr_b_seg", email="userb_seg@example.com", full_name="User B", hashed_password="pw")
        session.add_all([user_a, user_b])
        await session.commit()

    token_a = create_access_token({"sub": "usr_a_seg", "email": "usera_seg@example.com"})
    token_b = create_access_token({"sub": "usr_b_seg", "email": "userb_seg@example.com"})
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 2. User A creates Study A
        res_study_a = await client.post(
            "/api/studies",
            headers=headers_a,
            json={"prompt": "AI study planner for Bangladeshi students", "type": "interviews"},
        )
        assert res_study_a.status_code == 201
        study_a_id = res_study_a.json()["id"]

        # 3. User A uploads Dataset A (24 observed respondents; budgets rise with age)
        csv_rows = "\n".join(f"{18 + i // 2},{300 + i * 50},{3.0 + i * 0.25}" for i in range(24))
        csv_content = ("age,monthly_budget,study_hours\n" + csv_rows + "\n").encode()
        files = {"file": ("student_survey.csv", io.BytesIO(csv_content), "text/csv")}
        res_upload = await client.post(
            f"/api/studies/{study_a_id}/datasets/upload",
            headers=headers_a,
            data={"name": "Student Budget Survey"},
            files=files,
        )
        assert res_upload.status_code == 201

        # 4. User A checks readiness
        res_ready_a = await client.get(f"/api/studies/{study_a_id}/segmentation/readiness", headers=headers_a)
        assert res_ready_a.status_code == 200
        ready_data = res_ready_a.json()
        assert ready_data["can_run"] is True
        assert ready_data["total_records"] == 24

        # 5. User A triggers segmentation run
        res_run_a = await client.post(
            f"/api/studies/{study_a_id}/segmentation",
            headers=headers_a,
            json={"desired_clusters": 2},
        )
        assert res_run_a.status_code == 201, res_run_a.text
        run_data = res_run_a.json()
        run_id = run_data["run"]["id"]
        segments = run_data["segments"]
        assert len(segments) == 2
        assert [s["name"] for s in segments] == ["Lower-budget planners", "Higher-budget planners"]
        assert sum(s["population_count"] for s in segments) == 24  # every observed row is placed
        seg_1_id = segments[0]["id"]
        seg_2_id = segments[1]["id"]
        assert run_data["run"]["dataset_versions"] is not None

        # 6. User B creates Study B
        res_study_b = await client.post(
            "/api/studies",
            headers=headers_b,
            json={"prompt": "Study B for User B", "type": "concept"},
        )
        assert res_study_b.status_code == 201
        study_b_id = res_study_b.json()["id"]

        # 7. IDOR Tests: User B attempts to access User A's segmentation resources -> MUST return 404
        # a) Readiness check on Study A
        res_idor_ready = await client.get(f"/api/studies/{study_a_id}/segmentation/readiness", headers=headers_b)
        assert res_idor_ready.status_code == 404

        # b) Trigger segmentation on Study A
        res_idor_trigger = await client.post(f"/api/studies/{study_a_id}/segmentation", headers=headers_b, json={})
        assert res_idor_trigger.status_code == 404

        # c) List runs for Study A
        res_idor_runs = await client.get(f"/api/studies/{study_a_id}/segmentation/runs", headers=headers_b)
        assert res_idor_runs.status_code == 404

        # d) Get specific run from Study A
        res_idor_get_run = await client.get(f"/api/studies/{study_a_id}/segmentation/runs/{run_id}", headers=headers_b)
        assert res_idor_get_run.status_code == 404

        # e) List segments for Study A
        res_idor_segs = await client.get(f"/api/studies/{study_a_id}/segments", headers=headers_b)
        assert res_idor_segs.status_code == 404

        # f) Get segment detail from Study A
        res_idor_seg_detail = await client.get(f"/api/studies/{study_a_id}/segments/{seg_1_id}", headers=headers_b)
        assert res_idor_seg_detail.status_code == 404

        # g) Compare segments from Study A
        res_idor_compare = await client.post(
            f"/api/studies/{study_a_id}/segments/compare",
            headers=headers_b,
            json={"segment_ids": [seg_1_id, seg_2_id]},
        )
        assert res_idor_compare.status_code == 404

        # h) Delete run from Study A
        res_idor_delete = await client.delete(f"/api/studies/{study_a_id}/segmentation/runs/{run_id}", headers=headers_b)
        assert res_idor_delete.status_code == 404

        # 8. User A can successfully list, inspect, compare, and delete their own segments
        res_list_a = await client.get(f"/api/studies/{study_a_id}/segments", headers=headers_a)
        assert res_list_a.status_code == 200
        assert len(res_list_a.json()) == 2

        res_detail_a = await client.get(f"/api/studies/{study_a_id}/segments/{seg_1_id}", headers=headers_a)
        assert res_detail_a.status_code == 200
        assert res_detail_a.json()["id"] == seg_1_id

        res_compare_a = await client.post(
            f"/api/studies/{study_a_id}/segments/compare",
            headers=headers_a,
            json={"segment_ids": [seg_1_id, seg_2_id]},
        )
        assert res_compare_a.status_code == 200
        assert res_compare_a.json()["compared_count"] == 2

        res_del_a = await client.delete(f"/api/studies/{study_a_id}/segmentation/runs/{run_id}", headers=headers_a)
        assert res_del_a.status_code == 200
