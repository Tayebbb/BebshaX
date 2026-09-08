"""End-to-end integration tests for Dataset Sources API and grounded persona generation."""

from fastapi.testclient import TestClient


def test_datasets_upload_profiling_and_persona_generation_flow(
    api_test_app: TestClient, auth_headers
):
    """Ingestion is authenticated now: an anonymous upload used to be stamped
    with the shared anonymous tenant, which every other visitor can read."""
    csv_bytes = b"""student_id,name,role,age,monthly_budget,tech_level
1,Rahim,Student,21,350,Medium
2,Karim,Student,22,400,High
3,Sadia,Student,20,300,Medium
4,Tariq,Professional,28,1200,High
5,Farzana,Professional,32,1500,High
"""
    # 0. Anonymous ingestion is refused outright.
    anon = api_test_app.post(
        "/api/datasets/upload",
        files={"file": ("students.csv", csv_bytes, "text/csv")},
        data={"name": "Anonymous attempt"},
    )
    assert anon.status_code == 401

    # 1. Upload dataset
    files = {"file": ("students.csv", csv_bytes, "text/csv")}
    data = {"name": "Bangladesh Student & Pro Survey 2026", "description": "Student budget validation survey"}
    res = api_test_app.post("/api/datasets/upload", files=files, data=data, headers=auth_headers)
    assert res.status_code == 201
    created = res.json()
    ds_id = created["id"]
    assert created["name"] == "Bangladesh Student & Pro Survey 2026"
    assert created["row_count"] == 5
    assert created["column_count"] == 6
    assert len(created["segments"]) >= 1

    # 2. Get dataset by ID
    res = api_test_app.get(f"/api/datasets/{ds_id}", headers=auth_headers)
    assert res.status_code == 200
    fetched = res.json()
    assert fetched["id"] == ds_id
    assert "schema_metadata" in fetched
    assert "statistics" in fetched
    assert "segments" in fetched

    # 3. List datasets
    res = api_test_app.get("/api/datasets", headers=auth_headers)
    assert res.status_code == 200
    assert any(d["id"] == ds_id for d in res.json())

    # 3b. The uploader's dataset is NOT in the anonymous shared read pool.
    anon_list = api_test_app.get("/api/datasets")
    assert anon_list.status_code == 200
    assert all(d["id"] != ds_id for d in anon_list.json())
    assert api_test_app.get(f"/api/datasets/{ds_id}").status_code == 404

    # 4. Generate grounded personas from dataset — every persona is written by
    # the (fake) model. The shared route's scripted interview lines are cleared
    # so it answers persona JSON for all four; there is no offline template.
    fake_adapter = api_test_app.app.state.llm_adapters["pollinations"]
    for route in fake_adapter._routes.values():
        route.replies.clear()
    gen_res = api_test_app.post(
        f"/api/datasets/{ds_id}/generate-personas",
        json={"requested_count": 4, "business_name": "Price Tracker"},
        headers=auth_headers,
    )
    assert gen_res.status_code == 200, gen_res.text
    gen_data = gen_res.json()
    assert gen_data["requested_count"] == 4
    assert gen_data["generated_count"] == 4 and gen_data["failed_count"] == 0
    assert len(gen_data["personas"]) == 4
    assert gen_data["served_by"] == ["pollinations/deepseek-r1"]
    assert "distribution" in gen_data
    assert "validation_summary" in gen_data

    # 5. Deleting is a write: only the row's authenticated owner may destroy it.
    assert api_test_app.delete(f"/api/datasets/{ds_id}").status_code == 404
    assert api_test_app.delete(f"/api/datasets/{ds_id}", headers=auth_headers).status_code == 200
