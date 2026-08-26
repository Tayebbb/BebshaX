"""M5: business industry/target_market are real columns — description is user content."""

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient


def test_create_business_stores_real_columns(api_test_app: TestClient, auth_headers) -> None:
    resp = api_test_app.post(
        "/api/businesses",
        json={
            "name": "GigWheels",
            "description": "Fuel tracking for couriers.",
            "industry": "Logistics",
            "target_market": "Bangladesh couriers",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["industry"] == "Logistics"
    assert data["target_market"] == "Bangladesh couriers"
    # description stays pure user content — no metadata header
    assert data["description"] == "Fuel tracking for couriers."

    listed = {b["id"]: b for b in api_test_app.get("/api/businesses", headers=auth_headers).json()}
    assert listed[data["id"]]["industry"] == "Logistics"
    assert listed[data["id"]]["target_market"] == "Bangladesh couriers"


def test_description_starting_with_industry_is_not_corrupted(api_test_app: TestClient, auth_headers) -> None:
    # The audit's corruption case: user content that happens to start with "Industry:"
    desc = "Industry: reports are compiled quarterly by our analysts."
    resp = api_test_app.post("/api/businesses", json={"name": "ReportCo", "description": desc}, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["description"] == desc  # untouched
    assert data["industry"] is None  # honest null, not "General Enterprise"
    assert data["target_market"] is None

    listed = {b["id"]: b for b in api_test_app.get("/api/businesses", headers=auth_headers).json()}
    assert listed[data["id"]]["description"] == desc
    assert listed[data["id"]]["industry"] is None


def _load_migration():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "c4d5e6f7a8b9_m5_business_industry_target_market.py"
    )
    spec = importlib.util.spec_from_file_location("m5_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_parses_exact_legacy_header() -> None:
    m = _load_migration()
    ind, tm, desc = m._split_legacy_header(
        "Industry: Fintech | Target Market: Students\n\nA budgeting app."
    )
    assert (ind, tm, desc) == ("Fintech", "Students", "A budgeting app.")

    ind, tm, desc = m._split_legacy_header("Industry: Fintech\n\nA budgeting app.")
    assert (ind, tm, desc) == ("Fintech", None, "A budgeting app.")

    # TM-only creates existed too — the old writer emitted this form
    ind, tm, desc = m._split_legacy_header("Target Market: Students\n\nA budgeting app.")
    assert (ind, tm, desc) == (None, "Students", "A budgeting app.")


def test_migration_leaves_user_content_alone() -> None:
    m = _load_migration()
    # Header-line with unrecognized segments = user content, not the old format
    original = "Industry: reports are compiled | shared quarterly\n\nDetails follow."
    ind, tm, desc = m._split_legacy_header(original)
    assert (ind, tm) == (None, None)
    assert desc == original


def test_migration_refuses_overlong_values_as_user_content() -> None:
    # The old BusinessCreate bound was 256 chars — longer provably isn't legacy.
    m = _load_migration()
    original = "Industry: " + ("x" * 300)
    ind, tm, desc = m._split_legacy_header(original)
    assert (ind, tm) == (None, None)
    assert desc == original
