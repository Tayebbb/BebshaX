"""Production-readiness hardening regressions (2026-09 audit).

Covers: hosted-env config guards (demo_mode, email_from_address), the
neutralized Neon default + 503 when unconfigured, Settings-driven data
directories, the OpenRouter model-list override, and the deterministic report
template never inventing business claims.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from bebshax import config
from bebshax.config import Settings

_JWT = "x" * 48


# ---------------------------------------------------------------------------
# Config guards (fail-fast in production/staging, tolerant in development)
# ---------------------------------------------------------------------------


def _hosted_env(monkeypatch, **extra: str) -> None:
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", _JWT)
    monkeypatch.setenv("BEBSHAX_ENVIRONMENT", "production")
    monkeypatch.setenv("BEBSHAX_RESEND_API_KEY", "re_test_dummy")
    monkeypatch.setenv("BEBSHAX_EMAIL_FROM_ADDRESS", "noreply@example.com")
    monkeypatch.delenv("BEBSHAX_DEMO_MODE", raising=False)
    for k, v in extra.items():
        monkeypatch.setenv(k, v)


def test_demo_mode_refused_in_production(monkeypatch):
    """demo_mode seeds known credentials — production/staging must fail fast."""
    _hosted_env(monkeypatch, BEBSHAX_DEMO_MODE="true")
    with pytest.raises(ValueError, match="BEBSHAX_DEMO_MODE"):
        Settings(_env_file=None)


def test_demo_mode_allowed_in_development(monkeypatch):
    """The compose demo/exhibition profile (default development env) keeps working."""
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", _JWT)
    monkeypatch.setenv("BEBSHAX_ENVIRONMENT", "development")
    monkeypatch.setenv("BEBSHAX_DEMO_MODE", "true")
    assert Settings(_env_file=None).demo_mode is True


def test_email_from_address_required_in_production(monkeypatch):
    _hosted_env(monkeypatch)
    monkeypatch.delenv("BEBSHAX_EMAIL_FROM_ADDRESS", raising=False)
    with pytest.raises(ValueError, match="BEBSHAX_EMAIL_FROM_ADDRESS is required"):
        Settings(_env_file=None)


def test_email_from_address_optional_in_development(monkeypatch):
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", _JWT)
    monkeypatch.setenv("BEBSHAX_ENVIRONMENT", "development")
    monkeypatch.delenv("BEBSHAX_EMAIL_FROM_ADDRESS", raising=False)
    assert Settings(_env_file=None).email_from_address == ""


def test_neon_auth_url_has_no_baked_in_tenant(monkeypatch):
    """The default must never point at someone's live Neon tenant."""
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", _JWT)
    monkeypatch.delenv("BEBSHAX_NEON_AUTH_URL", raising=False)
    s = Settings(_env_file=None)
    assert s.neon_auth_url == ""


def test_db_pool_settings_default_and_override(monkeypatch):
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", _JWT)
    s = Settings(_env_file=None)
    assert (s.db_pool_size, s.db_max_overflow) == (5, 5)
    s2 = Settings(_env_file=None, db_pool_size=11, db_max_overflow=3)
    assert (s2.db_pool_size, s2.db_max_overflow) == (11, 3)


# ---------------------------------------------------------------------------
# Data directory resolution (BLOCKER 1)
# ---------------------------------------------------------------------------


def test_data_dir_defaults_match_previous_literals(monkeypatch):
    """Dev default is byte-identical to the old hardcoded CWD-relative paths."""
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", _JWT)
    for var in ("BEBSHAX_DATA_DIR", "BEBSHAX_UPLOAD_DIR", "BEBSHAX_PROCESSED_DIR"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.upload_dir_path == Path("data") / "uploads"
    assert s.processed_dir_path == Path("data") / "processed"


def test_data_dir_env_derives_both_subdirs(monkeypatch):
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", _JWT)
    s = Settings(_env_file=None, data_dir="/srv/bebshax-data")
    assert s.upload_dir_path == Path("/srv/bebshax-data") / "uploads"
    assert s.processed_dir_path == Path("/srv/bebshax-data") / "processed"


def test_explicit_upload_and_processed_dirs_win(monkeypatch):
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", _JWT)
    s = Settings(
        _env_file=None,
        data_dir="/srv/data",
        upload_dir="/mnt/uploads",
        processed_dir="/mnt/processed",
    )
    assert s.upload_dir_path == Path("/mnt/uploads")
    assert s.processed_dir_path == Path("/mnt/processed")


def test_upload_dir_resolved_from_settings_at_call_time(monkeypatch, tmp_path):
    """The service helpers must follow BEBSHAX_DATA_DIR, not a frozen literal."""
    import bebshax.datasets.discovery.engine as disc_engine
    import bebshax.datasets.service as ds_service
    import bebshax.persona.evidence as evidence_mod
    import bebshax.research.service as res_service

    consumers = (config, ds_service, disc_engine, res_service, evidence_mod)

    def _clear_all_setting_caches() -> None:
        # test_jwt_secret.py reloads bebshax.config, leaving consumer modules
        # bound to a stale get_settings object with its own lru_cache — clear
        # every bound reference, not just the current module's.
        for mod in consumers:
            mod.get_settings.cache_clear()

    root = tmp_path / "container-data"
    monkeypatch.setenv("BEBSHAX_DATA_DIR", str(root))
    _clear_all_setting_caches()
    try:
        expected = root / "uploads"
        assert ds_service._upload_dir() == expected
        assert disc_engine._upload_dir() == expected
        assert res_service._upload_dir() == expected
        assert evidence_mod.EvidenceStore()._dir == root / "processed"
    finally:
        _clear_all_setting_caches()


# ---------------------------------------------------------------------------
# Neon federated sign-in: 503 when unconfigured (S1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_neon_token_503_when_unconfigured(monkeypatch):
    from fastapi import HTTPException

    import bebshax.api.auth as auth_mod

    hermetic = Settings(_env_file=None, jwt_secret=_JWT, neon_auth_url="")
    monkeypatch.setattr(auth_mod, "get_settings", lambda: hermetic)

    with pytest.raises(HTTPException) as exc_info:
        await auth_mod.verify_neon_token("some-token")
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Neon authentication is not configured"


# ---------------------------------------------------------------------------
# OpenRouter model list override (S3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_openrouter_models_env_override(monkeypatch):
    from bebshax.llm.adapters.openrouter_adapter import DEFAULT_MODELS, OpenRouterAdapter

    adapter = OpenRouterAdapter(api_key="test-key-not-real")

    monkeypatch.setenv("BEBSHAX_OPENROUTER_MODELS", " a/x:free , b/y:free ,")
    assert [c.model for c in await adapter.candidates()] == ["a/x:free", "b/y:free"]

    monkeypatch.delenv("BEBSHAX_OPENROUTER_MODELS", raising=False)
    assert [c.model for c in await adapter.candidates()] == DEFAULT_MODELS


# ---------------------------------------------------------------------------
# Deterministic report template: absent data => omitted/None, never invented (S8)
# ---------------------------------------------------------------------------


def _template_report(evidence_claims=(), behavioral_results=()):
    from bebshax.research.report_service import StudyReportService

    study = SimpleNamespace(
        prompt="AI meal planner",
        title="Template Study",
        target_audience=None,
        pricing_hypothesis=None,
    )
    service = StudyReportService(session=None)
    return service._generate_deterministic_report(
        study=study,
        evidence_sources=[],
        evidence_claims=list(evidence_claims),
        datasets=[],
        segments=[],
        personas=[],
        conversations=[],
        interview_insights=[],
        behavioral_tests=[],
        behavioral_results=list(behavioral_results),
        version=1,
    )


def test_template_report_omits_invented_claims_when_data_absent():
    result = SimpleNamespace(
        decision="purchase_intent",
        decision_label=None,
        probability=0.42,
        persona_name="Nadia",
        objections=[],
        motivators=[],
    )
    report = _template_report(behavioral_results=[result])

    # No recorded objections/motivators -> None, not an invented business claim.
    row = report["behavioral_results"][0]
    assert row["key_objection"] is None
    assert row["key_motivator"] is None

    # No persona needs -> empty, no canned "frictionless setup"/pricing claims.
    assert report["customer_needs"] == []

    # No stored evidence claims -> no key findings at all.
    assert report["key_findings"] == []

    dumped = str(report)
    for invented in (
        "Price sensitivity",
        "Time savings & convenience",
        "Frictionless setup",
        "Predictable, fair pricing",
        "Hypothesis:",
    ):
        assert invented not in dumped, f"template invented claim: {invented!r}"


def test_template_key_findings_come_from_stored_claims():
    claim = SimpleNamespace(
        claim_text="74% of university students spend less than 3,000 BDT per month on lunch",
        confidence=0.88,
        supporting_source_ids=["src_01"],
    )
    report = _template_report(evidence_claims=[claim])
    assert report["key_findings"] == [claim.claim_text]
