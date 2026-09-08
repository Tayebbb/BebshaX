"""Legacy persona HTTP contracts with real tiny-model inference and sqlite."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_client(ml_api_app: TestClient, ml_auth_headers: dict[str, str]):
    return ml_api_app, ml_auth_headers


async def test_full_persona_flow_over_http(app_client, ml_training_records) -> None:
    client, headers = app_client
    created = client.post(
        "/api/businesses", json={"name": "QuickBite", "description": "Food delivery in Dhaka"},
        headers=headers,
    )
    assert created.status_code == 201
    business_id = created.json()["id"]

    listed = client.get("/api/businesses", headers=headers)
    assert any(b["id"] == business_id for b in listed.json())

    generated = client.post(f"/api/businesses/{business_id}/personas", json={}, headers=headers)
    assert generated.status_code == 201, generated.text
    persona = generated.json()
    source = next(record for record in ml_training_records if record.record_id == persona["detailed_attributes"]["ml_provenance"]["record_id"])
    assert persona["name"] == (source.name or f"Synthetic profile {source.record_id}")
    assert persona["generation_model"].startswith("bebshax-persona-ml/")
    assert all(attribute["provenance_class"] == "SYNTHETIC" for attribute in persona["attributes"])

    fetched = client.get(f"/api/personas/{persona['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["occupation"] == source.occupation
    assert fetched.json()["detailed_attributes"]["source_documents"] == source.documents
    assert client.app.state.ml_test_llm.calls == []


async def test_unknown_business_and_persona_return_404(app_client) -> None:
    client, headers = app_client
    assert client.post("/api/businesses/nope/personas", json={}, headers=headers).status_code == 404
    assert client.get("/api/personas/nope").status_code == 404

