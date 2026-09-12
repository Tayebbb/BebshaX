"""M1 regression tests: /api/evaluation/metrics must report measured values
(provenance aggregates, judged gate reports) and null — never fabricated
numbers — when there is no underlying data."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from bebshax.api.evaluation import get_evaluation_metrics
from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base, LLMRequests, Personas
from bebshax.llm.types import TaskType
from bebshax.persona.orm import PersonaAttributes, PersonaDetails

_DEVELOPER_ID = "usr_evaluation_developer"


def _developer_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(_DEVELOPER_ID)}"}


@pytest.fixture
async def eval_app(tmp_path, monkeypatch):
    # Point the gate-report reader at an isolated dir (empty by default).
    monkeypatch.setenv("BEBSHAX_METADATA_DIR", str(tmp_path / "metadata"))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'eval.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(Users(
            id=_DEVELOPER_ID, email="evaluation-developer@example.test",
            full_name="Evaluation Developer", hashed_password="unused-fixture-hash",
            role="developer", is_active=True, is_verified=True,
        ))
        await session.commit()

    from bebshax.main import create_app
    from bebshax.config import Settings

    app = create_app()
    settings_options: dict[str, Any] = {"_env_file": None, "environment": "development"}
    app.state.settings = Settings(**settings_options)
    app.state.db_sessionmaker = maker
    try:
        yield app, maker, tmp_path
    finally:
        await engine.dispose()


async def _get_metrics(app) -> dict:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/evaluation/metrics", headers=_developer_headers())
        assert res.status_code == 200
        return res.json()


async def test_evaluation_requires_authentication(eval_app):
    app, _, _ = eval_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/evaluation/metrics")
    assert response.status_code == 401


async def test_evaluation_denies_a_non_developer_database_role(eval_app):
    app, maker, _ = eval_app
    async with maker() as session:
        user = await session.get(Users, _DEVELOPER_ID)
        assert user is not None
        user.role = "user"
        await session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/evaluation/metrics", headers=_developer_headers())
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_empty_db_reports_null_not_fake_perfection(eval_app):
    app, _, _ = eval_app
    data = await _get_metrics(app)
    health = data["overall_health"]
    assert health["total_personas_generated"] == 0
    # No data → null. The audited endpoint claimed 1.0 validity/consistency.
    assert health["schema_validity_rate"] is None
    assert health["consistency_pass_rate"] is None
    assert health["avg_grounding_ratio"] is None
    assert health["avg_latency_ms"] is None
    assert data["pools"] == []
    assert data["quality_gate"] is None
    assert "routing_strategies" not in data


@pytest.mark.asyncio
async def test_pool_rows_are_measured_from_provenance(eval_app):
    app, maker, _ = eval_app
    ok = {"failure_kind": None, "success": True}
    fail = {"failure_kind": "TIMEOUT", "success": False}
    malformed = {"failure_kind": "MALFORMED_RESPONSE", "success": False}
    async with maker() as session:
        session.add_all(
            [
                # conversation pool: 2 requests, 1 ollama-served, 1 fallback chain
                LLMRequests(
                    request_id="r1", task=TaskType.PERSONA_RESPONSE, pool="conversation",
                    success=True, total_latency_ms=1000.0,
                    attempts=[{**ok, "provider": "ollama", "model": "historical"}],
                    served_by_provider="ollama",
                ),
                LLMRequests(
                    request_id="r2", task=TaskType.PERSONA_RESPONSE, pool="conversation",
                    success=True, total_latency_ms=3000.0,
                    attempts=[{**fail, "provider": "groq", "model": "first"},
                              {**ok, "provider": "openrouter", "model": "second"}],
                    served_by_provider="openrouter",
                ),
                # structured pool: 1 failed persona-gen with a malformed attempt
                LLMRequests(
                    request_id="r3", task=TaskType.PERSONA_GENERATION, pool="structured",
                    success=False, total_latency_ms=500.0, attempts=[malformed, malformed],
                    served_by_provider=None,
                ),
                # structured pool: 1 clean persona-gen
                LLMRequests(
                    request_id="r4", task=TaskType.PERSONA_GENERATION, pool="structured",
                    success=True, total_latency_ms=1500.0, attempts=[ok],
                    served_by_provider="freellmpool",
                ),
            ]
        )
        await session.commit()

    data = await _get_metrics(app)
    pools = {p["pool"]: p for p in data["pools"]}
    conv = pools["conversation"]
    assert conv["requests"] == 2
    assert conv["success_rate"] == 1.0
    assert conv["avg_latency_ms"] == 2000.0
    assert conv["fallback_rate"] == 0.5  # r2 took 2 attempts
    assert conv["local_serve_rate"] is None
    assert conv["historical_ollama_provider_rate"] == 0.5
    structured = pools["structured"]
    assert structured["requests"] == 2
    assert structured["success_rate"] == 0.5
    assert structured["local_serve_rate"] is None
    assert structured["historical_ollama_provider_rate"] == 0.0

    health = data["overall_health"]
    # schema validity: 1 of 2 persona-gen requests emitted MALFORMED_RESPONSE
    assert health["schema_validity_rate"] == 0.5
    assert health["avg_latency_ms"] == 1500.0  # mean of 1000/3000/500/1500


@pytest.mark.asyncio
async def test_consistency_and_grounding_come_from_persona_artifacts(eval_app):
    app, maker, _ = eval_app
    async with maker() as session:
        session.add_all(
            [
                Personas(id="p1", owner_id="usr_system_holder", name="P1", version=1),
                Personas(id="p2", owner_id="usr_system_holder", name="P2", version=1),
                PersonaDetails(persona_id="p1", age=31, occupation="nurse", location="Dhaka",
                               income_range="30-40k", education="BSc", description="d", warnings=[]),
                PersonaDetails(persona_id="p2", age=44, occupation="driver", location="Khulna",
                               income_range="20-30k", education="HSC", description="d",
                               warnings=["income contradicts occupation"]),
                PersonaAttributes(id="a1", persona_id="p1", key="occupation",
                                  value="nurse", provenance_class="OBSERVED"),
                PersonaAttributes(id="a2", persona_id="p1", key="hobby",
                                  value="cricket", provenance_class="SYNTHETIC"),
            ]
        )
        await session.commit()

    health = (await _get_metrics(app))["overall_health"]
    assert health["total_personas_generated"] == 2
    assert health["consistency_pass_rate"] == 0.5  # p2 has a warning
    assert health["avg_grounding_ratio"] == 0.5  # 1 OBSERVED of 2 attrs


@pytest.mark.asyncio
async def test_quality_gate_surfaces_latest_judged_report(eval_app):
    app, _, tmp_path = eval_app
    meta = tmp_path / "metadata"
    meta.mkdir()
    report = {
        "generated_at": "2026-08-26T17:56:33+00:00",
        "bar": 8.0,
        "rubric_weights": {"persona_consistency": 0.25},
        "arm_a": {"model": "ollama/llama3.2:3b", "tag": "local/llama3.2:3b",
                  "weighted": 9.65, "avg_ms": 6067, "dims": {"naturalness": 9}, "turns": []},
        "arm_b": {"model": "freellmpool", "tag": "freellmpool/fast",
                  "weighted": 8.25, "avg_ms": 52988, "dims": {}, "turns": []},
        "judge": {"route": "llm7/codestral-latest", "notes": "A wins."},
    }
    (meta / "local_3b_gate_20260826_235633.json").write_text(json.dumps(report), encoding="utf-8")
    # an older report that must NOT be picked
    older = dict(report, generated_at="2026-08-20T00:00:00+00:00")
    (meta / "local_3b_gate_20260820_000000.json").write_text(json.dumps(older), encoding="utf-8")

    gate = (await _get_metrics(app))["quality_gate"]
    assert gate["source_file"] == "local_3b_gate_20260826_235633.json"
    assert gate["bar"] == 8.0
    assert gate["arms"][0]["weighted_score"] == 9.65
    assert gate["arms"][1]["avg_latency_ms"] == 52988
    assert gate["judge_route"] == "llm7/codestral-latest"


@pytest.mark.asyncio
async def test_unreadable_gate_report_degrades_to_null(eval_app):
    app, _, tmp_path = eval_app
    meta = tmp_path / "metadata"
    meta.mkdir()
    (meta / "local_3b_gate_bad.json").write_text("{not json", encoding="utf-8")
    assert (await _get_metrics(app))["quality_gate"] is None


@pytest.mark.asyncio
async def test_wrong_shape_gate_falls_back_to_older_valid_report(eval_app):
    app, _, tmp_path = eval_app
    meta = tmp_path / "metadata"
    meta.mkdir()
    good = {
        "generated_at": "2026-08-20T00:00:00+00:00", "bar": 8.0,
        "arm_a": {"tag": "local", "weighted": 9.0, "avg_ms": 5000},
        "arm_b": {"tag": "cloud", "weighted": 8.0, "avg_ms": 40000},
        "judge": {"route": "x", "notes": "ok"},
    }
    (meta / "local_3b_gate_20260820_000000.json").write_text(json.dumps(good), encoding="utf-8")
    # newest file is valid JSON but the wrong shape — must not 500, must
    # fall back to the older readable report
    (meta / "local_3b_gate_20260826_000000.json").write_text("[]", encoding="utf-8")

    gate = (await _get_metrics(app))["quality_gate"]
    assert gate is not None
    assert gate["source_file"] == "local_3b_gate_20260820_000000.json"
    assert gate["arms"][0]["weighted_score"] == 9.0


@pytest.mark.parametrize("attempts", [[], [{"success": False, "failure_kind": "TIMEOUT"}],
                                      [{"success": True, "cached": True}]])
async def test_unmeasured_generation_never_claims_schema_validity(eval_app, attempts):
    app, maker, _ = eval_app
    async with maker() as session:
        session.add(LLMRequests(request_id="unmeasured", task=TaskType.PERSONA_GENERATION,
                                pool="reasoning", attempts=attempts, success=False))
        await session.commit()
    health = (await _get_metrics(app))["overall_health"]
    assert health["schema_validity_rate"] is None
    assert health["schema_evaluable_requests"] == 0
    assert health["schema_unknown_requests"] == 1


async def test_same_route_retry_is_not_a_provider_fallback(eval_app):
    app, maker, _ = eval_app
    async with maker() as session:
        session.add(LLMRequests(
            request_id="retry", task=TaskType.PERSONA_RESPONSE, pool="conversation", success=True,
            attempts=[
                {"provider": "openrouter", "model": "test", "success": False, "failure_kind": "CONNECTION"},
                {"provider": "openrouter", "model": "test", "success": True},
            ],
        ))
        await session.commit()
    pool = (await _get_metrics(app))["pools"][0]
    assert pool["fallback_rate"] == 0.0
    assert pool["fallback_evaluable_requests"] == 1


async def test_inner_remote_attempts_count_as_fallback_without_outer_retry(eval_app):
    app, maker, _ = eval_app
    async with maker() as session:
        session.add(LLMRequests(
            request_id="inner", task=TaskType.PERSONA_RESPONSE, pool="conversation", success=True,
            attempts=[{"provider": "groq", "model": "answer", "via": "freellmpool/auto", "success": True,
                       "observations": [
                           {"provider": "cerebras", "requested_model": "first", "outcome": "failed", "consumption": "unknown"},
                           {"provider": "groq", "requested_model": "answer", "outcome": "succeeded", "consumption": "known"},
                       ]}],
        ))
        await session.commit()
    pool = (await _get_metrics(app))["pools"][0]
    assert pool["fallback_rate"] == 1.0
    assert pool["fallback_evaluable_requests"] == 1


async def test_global_evaluation_is_not_exposed_outside_development(eval_app):
    from types import SimpleNamespace

    app, _, _ = eval_app
    app.state.settings = SimpleNamespace(environment="test")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/evaluation/metrics", headers=_developer_headers())
    assert response.status_code == 404


async def test_cached_answer_is_not_current_provider_availability(eval_app):
    app, maker, _ = eval_app
    async with maker() as session:
        session.add(LLMRequests(
            request_id="cached-status", task=TaskType.PERSONA_RESPONSE, pool="conversation", success=True,
            attempts=[{"provider": "groq", "model": "test", "cached": True, "success": True}],
        ))
        await session.commit()
    assert (await _get_metrics(app))["pools"][0]["status"] == "unknown"


@pytest.mark.parametrize("provider, historical_rate", [("ollama", 1.0), ("freellmpool", 0.0)])
async def test_provider_labels_do_not_establish_historical_locality(eval_app, provider, historical_rate):
    app, maker, _ = eval_app
    async with maker() as session:
        session.add(LLMRequests(
            request_id="ambiguous-locality", task=TaskType.PERSONA_RESPONSE,
            pool="conversation", success=True, served_by_provider=provider,
            attempts=[{"provider": provider, "model": "historical", "success": True}],
        ))
        await session.commit()
    data = await _get_metrics(app)
    [pool] = data["pools"]
    assert pool["local_serve_rate"] is None
    assert pool["historical_ollama_provider_rate"] == historical_rate
    assert data["metrics_window"]["route_kind_measured"] is False


async def test_cancelled_latest_attempt_stays_unknown_in_a_bounded_metrics_window(eval_app, monkeypatch):
    app, maker, _ = eval_app
    monkeypatch.setattr("bebshax.api.evaluation._METRICS_SCAN_LIMIT", 1)
    now = datetime.now(timezone.utc)
    async with maker() as session:
        session.add_all([
            LLMRequests(
                request_id="older-observed-success", task=TaskType.PERSONA_RESPONSE,
                pool="conversation", success=True, total_latency_ms=9000,
                created_at=now - timedelta(minutes=10), served_by_provider="openrouter",
                attempts=[{"provider": "openrouter", "model": "older", "success": True}],
            ),
            LLMRequests(
                request_id="latest-cancelled", task=TaskType.PERSONA_GENERATION,
                pool="conversation", success=False, total_latency_ms=1000, created_at=now,
                attempts=[{
                    "provider": "freellmpool", "model": "auto", "success": False,
                    "observations": [{
                        "provider": "kilo", "requested_model": "verified-model",
                        "outcome": "aborted", "consumption": "unknown", "failure_kind": None,
                    }],
                }],
            ),
        ])
        await session.commit()
    data = await get_evaluation_metrics(Request({"type": "http", "method": "GET", "app": app}))
    assert data["metrics_window"]["truncated"] is True
    assert data["metrics_window"]["requests"] == 1
    assert data["overall_health"]["avg_latency_ms"] == 1000
    assert data["overall_health"]["schema_validity_rate"] is None
    assert data["overall_health"]["schema_unknown_requests"] == 1
    assert data["pools"][0]["status"] == "unknown"


async def test_unwired_metrics_leave_unmeasured_values_unknown(eval_app):
    app, _, _ = eval_app
    app.state.db_sessionmaker = None
    data = await get_evaluation_metrics(Request({"type": "http", "method": "GET", "app": app}))
    assert data["overall_health"]["total_personas_generated"] is None
    assert data["overall_health"]["avg_latency_ms"] is None
    assert data["pools"] == []
    assert data["metrics_window"]["truncated"] is False
