"""End-to-end integration tests for Dataset Sources API and grounded persona generation."""

from fastapi.testclient import TestClient


def test_datasets_upload_profiling_and_persona_generation_flow(
    ml_api_app: TestClient, ml_auth_headers
):
    """Ingestion is authenticated now: an anonymous upload used to be stamped
    with the shared anonymous tenant, which every other visitor can read."""
    csv_bytes = b"""student_id,name,role,age,monthly_budget,tech_level
1,Rahim,Student,21,350,Medium
2,Karim,Student,24,400,High
3,Sadia,Student,27,300,Medium
4,Tariq,Professional,30,1200,High
5,Farzana,Professional,33,1500,High
"""
    # 0. Anonymous ingestion is refused outright.
    anon = ml_api_app.post(
        "/api/datasets/upload",
        files={"file": ("students.csv", csv_bytes, "text/csv")},
        data={"name": "Anonymous attempt"},
    )
    assert anon.status_code == 401

    # 1. Upload dataset
    files = {"file": ("students.csv", csv_bytes, "text/csv")}
    data = {"name": "Bangladesh Student & Pro Survey 2026", "description": "Student budget validation survey"}
    res = ml_api_app.post("/api/datasets/upload", files=files, data=data, headers=ml_auth_headers)
    assert res.status_code == 201
    created = res.json()
    ds_id = created["id"]
    assert created["name"] == "Bangladesh Student & Pro Survey 2026"
    assert created["row_count"] == 5
    assert created["column_count"] == 6
    assert len(created["segments"]) >= 1

    # 2. Get dataset by ID
    res = ml_api_app.get(f"/api/datasets/{ds_id}", headers=ml_auth_headers)
    assert res.status_code == 200
    fetched = res.json()
    assert fetched["id"] == ds_id
    assert "schema_metadata" in fetched
    assert "statistics" in fetched
    assert "segments" in fetched

    # 3. List datasets
    res = ml_api_app.get("/api/datasets", headers=ml_auth_headers)
    assert res.status_code == 200
    assert any(d["id"] == ds_id for d in res.json())

    # 3b. The uploader's dataset is NOT in the anonymous shared read pool.
    anon_list = ml_api_app.get("/api/datasets")
    assert anon_list.status_code == 200
    assert all(d["id"] != ds_id for d in anon_list.json())
    assert ml_api_app.get(f"/api/datasets/{ds_id}").status_code == 404

    gen_res = ml_api_app.post(
        f"/api/datasets/{ds_id}/generate-personas",
        json={"requested_count": 4, "business_name": "Price Tracker", "business_description": "Meal budget and delivery tracking"},
        headers=ml_auth_headers,
    )
    assert gen_res.status_code == 200, gen_res.text
    gen_data = gen_res.json()
    assert gen_data["requested_count"] == 4
    assert gen_data["generated_count"] == 4 and gen_data["failed_count"] == 0
    assert len(gen_data["personas"]) == 4
    assert gen_data["served_by"] and all(model.startswith("bebshax-persona-ml/") for model in gen_data["served_by"])
    assert ml_api_app.app.state.ml_test_llm.calls == []
    assert "distribution" in gen_data
    assert "validation_summary" in gen_data

    # 5. Deleting is a write: only the row's authenticated owner may destroy it.
    assert ml_api_app.delete(f"/api/datasets/{ds_id}").status_code == 404
    assert ml_api_app.delete(f"/api/datasets/{ds_id}", headers=ml_auth_headers).status_code == 200
