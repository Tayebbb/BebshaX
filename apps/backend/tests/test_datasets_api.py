"""End-to-end integration tests for Dataset Sources API and grounded persona generation."""

import io
import pytest
from httpx import ASGITransport, AsyncClient

from bebshax.main import app


@pytest.mark.asyncio
async def test_datasets_upload_profiling_and_persona_generation_flow():
    csv_bytes = b"""student_id,name,role,age,monthly_budget,tech_level
1,Rahim,Student,21,350,Medium
2,Karim,Student,22,400,High
3,Sadia,Student,20,300,Medium
4,Tariq,Professional,28,1200,High
5,Farzana,Professional,32,1500,High
"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Upload dataset
        files = {"file": ("students.csv", csv_bytes, "text/csv")}
        data = {"name": "Bangladesh Student & Pro Survey 2026", "description": "Student budget validation survey"}
        res = await client.post("/api/datasets/upload", files=files, data=data)
        assert res.status_code == 201
        created = res.json()
        ds_id = created["id"]
        assert created["name"] == "Bangladesh Student & Pro Survey 2026"
        assert created["row_count"] == 5
        assert created["column_count"] == 6
        assert len(created["segments"]) >= 1

        # 2. Get dataset by ID
        res = await client.get(f"/api/datasets/{ds_id}")
        assert res.status_code == 200
        fetched = res.json()
        assert fetched["id"] == ds_id
        assert "schema_metadata" in fetched
        assert "statistics" in fetched
        assert "segments" in fetched

        # 3. List datasets
        res = await client.get("/api/datasets")
        assert res.status_code == 200
        all_ds = res.json()
        assert any(d["id"] == ds_id for d in all_ds)

        # 4. Generate grounded personas from dataset
        gen_res = await client.post(
            f"/api/datasets/{ds_id}/generate-personas",
            json={"requested_count": 4, "business_name": "Price Tracker"},
        )
        assert gen_res.status_code == 200
        gen_data = gen_res.json()
        assert gen_data["requested_count"] == 4
        assert gen_data["generated_count"] == 4
        assert len(gen_data["personas"]) == 4
        assert "distribution" in gen_data
        assert "validation_summary" in gen_data

        # 5. Deleting is a write: the shared pool is readable by everyone but
        # destroyable only by the row's authenticated owner, so this anonymous
        # upload can no longer be deleted by the next anonymous visitor.
        del_res = await client.delete(f"/api/datasets/{ds_id}")
        assert del_res.status_code == 404
