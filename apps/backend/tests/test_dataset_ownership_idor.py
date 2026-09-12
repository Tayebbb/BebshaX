import io
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base, Studies, DatasetSources
from bebshax.main import app
from bebshax.datasets.parser import parse_dataset_bytes
from bebshax.datasets.profiler import profile_dataset


@pytest.mark.asyncio
async def test_dataset_multi_user_idor_isolation():
    """
    Verify strict user-scoped dataset access and IDOR protection.
    User B must receive 404 when attempting to view, preview, refresh, or delete User A's datasets or study datasets.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_sessionmaker = session_maker

    # 1. Create User A and User B in database
    async with session_maker() as session:
        user_a = Users(id="usr_a_test", email="usera_dataset@example.com", full_name="User A", hashed_password="pw", is_verified=True)
        user_b = Users(id="usr_b_test", email="userb_dataset@example.com", full_name="User B", hashed_password="pw", is_verified=True)
        session.add_all([user_a, user_b])
        await session.commit()

    token_a = create_access_token({"sub": "usr_a_test", "email": "usera_dataset@example.com"})
    token_b = create_access_token({"sub": "usr_b_test", "email": "userb_dataset@example.com"})
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 2. User A creates a study
        res_study = await client.post(
            "/api/studies",
            headers=headers_a,
            json={"prompt": "Student research study for User A", "type": "interviews"},
        )
        assert res_study.status_code == 201, res_study.text
        study_a_id = res_study.json()["id"]

        # 3. User A uploads a dataset to their study
        csv_content = b"age,monthly_budget,occupation\n21,450,Student\n22,500,Student\n19,350,Candidate\n24,800,Tutor\n"
        files = {"file": ("student_data.csv", io.BytesIO(csv_content), "text/csv")}
        data = {"name": "User A Student Data", "description": "Demographic study"}

        res_upload = await client.post(
            f"/api/studies/{study_a_id}/datasets/upload",
            headers=headers_a,
            data=data,
            files=files,
        )
        assert res_upload.status_code == 201, res_upload.text
        dataset_a = res_upload.json()
        dataset_a_id = dataset_a["id"]
        assert dataset_a["row_count"] == 4
        assert dataset_a["column_count"] == 3
        assert dataset_a["content_hash"] is not None

        # 4. User A can list and view their dataset preview
        res_list_a = await client.get(f"/api/studies/{study_a_id}/datasets", headers=headers_a)
        assert res_list_a.status_code == 200
        assert len(res_list_a.json()) == 1
        assert res_list_a.json()[0]["id"] == dataset_a_id

        res_preview_a = await client.get(
            f"/api/studies/{study_a_id}/datasets/{dataset_a_id}/preview?offset=0&limit=2",
            headers=headers_a,
        )
        assert res_preview_a.status_code == 200
        preview = res_preview_a.json()
        assert len(preview["rows"]) == 2
        assert preview["total_rows"] == 4

        # 5. IDOR CHECK: User B attempts to access User A's study datasets -> 404
        res_list_b = await client.get(f"/api/studies/{study_a_id}/datasets", headers=headers_b)
        assert res_list_b.status_code == 404, "User B should not see User A's study datasets"

        # 6. IDOR CHECK: User B attempts to preview User A's dataset -> 404
        res_preview_b = await client.get(
            f"/api/studies/{study_a_id}/datasets/{dataset_a_id}/preview",
            headers=headers_b,
        )
        assert res_preview_b.status_code == 404

        # 7. IDOR CHECK: User B attempts to get dataset directly -> 404
        res_get_b = await client.get(f"/api/datasets/{dataset_a_id}", headers=headers_b)
        assert res_get_b.status_code == 404

        # 8. IDOR CHECK: User B attempts to refresh User A's dataset -> 404
        res_refresh_b = await client.post(
            f"/api/studies/{study_a_id}/datasets/{dataset_a_id}/refresh",
            headers=headers_b,
        )
        assert res_refresh_b.status_code == 404

        # 9. IDOR CHECK: User B attempts to delete User A's dataset -> 404
        res_del_b = await client.delete(
            f"/api/studies/{study_a_id}/datasets/{dataset_a_id}",
            headers=headers_b,
        )
        assert res_del_b.status_code == 404

        # Verify dataset still exists for User A
        res_check_a = await client.get(f"/api/datasets/{dataset_a_id}", headers=headers_a)
        assert res_check_a.status_code == 200

        # User A deletes their dataset -> 204
        res_del_a = await client.delete(
            f"/api/studies/{study_a_id}/datasets/{dataset_a_id}",
            headers=headers_a,
        )
        assert res_del_a.status_code == 200
        assert res_del_a.json()["status"] == "deleted"


def test_deterministic_profiler_csv_json_statistics():
    """Verify deterministic math calculations and data quality warning detections across CSV & JSON."""
    csv_raw = b"age,income,role\n20,300,student\n22,500,student\n20,300,student\n,700,intern\n25,-50,engineer\n"
    cols, records = parse_dataset_bytes(csv_raw, file_type="csv")
    assert len(records) == 5
    assert cols == ["age", "income", "role"]

    schema, stats = profile_dataset(cols, records)
    overview = stats["overview"]
    assert overview["row_count"] == 5
    assert overview["column_count"] == 3
    assert overview["duplicate_rows"] == 1  # (20, 300, 'student') occurs twice
    assert overview["duplicate_rows_percentage"] == 20.0
    assert overview["missing_values_percentage"] > 0

    # Check warnings
    warnings = stats["warnings"]
    assert any("duplicate" in w.lower() for w in warnings)
    assert any("negative" in w.lower() for w in warnings)

    # Check numeric stats
    numeric = stats["numeric"]
    assert "income" in numeric
    assert numeric["income"]["count"] == 5
    assert numeric["income"]["min"] == -50.0
    assert numeric["income"]["max"] == 700.0

    # Check categorical stats
    categorical = stats["categorical"]
    assert "role" in categorical
    assert categorical["role"]["unique_categories"] == 3
    assert categorical["role"]["percentages"]["student"] == 60.0


def test_deterministic_profiler_json_parsing():
    """Verify JSON array parsing and deterministic statistics calculation."""
    json_raw = b'[{"category": "A", "price": 100}, {"category": "B", "price": 200}, {"category": "A", "price": 150}]'
    cols, records = parse_dataset_bytes(json_raw, file_type="json")
    assert len(records) == 3
    assert "category" in cols and "price" in cols

    schema, stats = profile_dataset(cols, records)
    assert stats["overview"]["row_count"] == 3
    assert stats["overview"]["duplicate_rows"] == 0
    assert stats["numeric"]["price"]["mean"] == 150.0
