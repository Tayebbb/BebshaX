from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from bebshax.llm.governance import RemoteProcessingPolicy

if TYPE_CHECKING:
    from bebshax_persona_ml.provenance import ExpectedArtifactManifest

_PROJECT_ROOT = Path(__file__).resolve().parents[3]

BURNED_JWT_SECRET = "bebshax-super-secret-jwt-signing-key-2026-auth-v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BEBSHAX_", env_file=None, extra="ignore"
    )


    app_name: str = "BebshaX"
    environment: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    demo_mode: bool = False
    log_level: str = "INFO"
    provider_config_path: Path = _PROJECT_ROOT / "providers.toml"
    # NoDecode: a blank variable (env templates, hosting dashboards) must read as
    # "unset" rather than a JSON decode failure that refuses to boot.
    remote_processing_policy: Annotated[RemoteProcessingPolicy, NoDecode] = Field(
        default_factory=RemoteProcessingPolicy
    )
    runtime_shutdown_timeout_s: float = Field(default=15.0, gt=0, le=120)

    @model_validator(mode="before")
    @classmethod
    def blank_processing_policy_is_unset(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw = data.get("remote_processing_policy")
            if isinstance(raw, str) and not raw.strip():
                return {key: value for key, value in data.items() if key != "remote_processing_policy"}
        return data

    @field_validator("remote_processing_policy", mode="before")
    @classmethod
    def parse_processing_policy_json(cls, value: Any) -> Any:
        return json.loads(value) if isinstance(value, str) else value

    # Filesystem roots for uploaded/processed datasets. Relative paths resolve
    # against the process CWD (dev: repo root -> data/). Containers set
    # BEBSHAX_DATA_DIR to a writable, volume-backed absolute path.
    data_dir: str = "data"
    upload_dir: str | None = None  # default: <data_dir>/uploads
    processed_dir: str | None = None  # default: <data_dir>/processed
    ml_persona_artifact_dir: str | None = None
    ml_persona_enabled: bool = True
    ml_persona_required: bool = False
    ml_persona_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("provider_config_path", mode="after")
    @classmethod
    def provider_path_absolute(cls, value: Path) -> Path:
        return (value if value.is_absolute() else _PROJECT_ROOT / value).resolve()

    @property
    def expected_ml_persona_manifest(self) -> ExpectedArtifactManifest | None:
        from bebshax_persona_ml.provenance import ExpectedArtifactManifest

        if self.ml_persona_manifest_sha256 is None:
            return None
        return ExpectedArtifactManifest(metadata_sha256=self.ml_persona_manifest_sha256)

    @property
    def upload_dir_path(self) -> Path:
        return Path(self.upload_dir) if self.upload_dir else Path(self.data_dir) / "uploads"

    @property
    def processed_dir_path(self) -> Path:
        return Path(self.processed_dir) if self.processed_dir else Path(self.data_dir) / "processed"

    @property
    def ml_persona_artifact_path(self) -> Path:
        if self.ml_persona_artifact_dir:
            return Path(self.ml_persona_artifact_dir)
        return self.processed_dir_path / "ml_persona" / "model"

    # M6: explicit origins — wildcard + allow_credentials is invalid per the
    # Fetch spec and unsafe. Comma-separated; override via BEBSHAX_CORS_ORIGINS.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,https://bebshax-frontend.vercel.app"
    # Only local dev ports by default. Deployed frontends must be listed
    # explicitly in BEBSHAX_CORS_ORIGINS — a wildcard here combined with
    # credentialed requests would let any origin act as a logged-in user.
    cors_origin_regex: str = r"http://localhost:\d+|http://127\.0\.0\.1:\d+"
    frontend_base_url: str = "http://localhost:5173"
    resend_api_key: str | None = None
    # No default sender: Resend refuses unverified domains, so a shipped
    # literal only produces silent delivery failures. Required in prod/staging.
    email_from_address: str = ""
    smtp_host: str = "smtp-relay.brevo.com"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None

    @property
    def active_smtp_password(self) -> str | None:
        password = (self.smtp_password or "").strip()
        return password or None
    stripe_secret_key: str | None = None
    stripe_publishable_key: str | None = None
    stripe_webhook_secret: str | None = None
    # Optional Stripe Dashboard price ids; unset keeps the inline price_data path.
    stripe_price_id_pro: str | None = None
    stripe_price_id_enterprise: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


    database_url: str = "postgresql+asyncpg://bebshax:bebshax@localhost:5433/bebshax"
    db_pool_size: int = 5
    db_max_overflow: int = 5

    @property
    def sync_database_url(self) -> str:
        url = self.database_url
        if "+asyncpg" in url:
            return url.replace("+asyncpg", "")
        if "+aiosqlite" in url:
            return url.replace("+aiosqlite", "")
        return url

    embedding_backend: Literal["local", "freellmpool"] = "local"
    embedding_model: str | None = None

    @model_validator(mode="after")
    def runtime_configuration_valid(self) -> Settings:
        if self.embedding_backend == "freellmpool" and not (self.embedding_model or "").strip():
            raise ValueError("BEBSHAX_EMBEDDING_MODEL must pin the remote embedding model")
        if self.ml_persona_required and not self.ml_persona_enabled:
            raise ValueError("A required persona feature cannot be disabled")
        return self

    # B4: no default — a shipped signing key lets anyone forge tokens for every
    # deployment that forgets to set the env var. Empty fails the validator below.
    jwt_secret: str = ""
    jwt_secret_previous: str | None = None  # rotation grace window only
    jwt_issuer: str = "bebshax-api"
    jwt_audience: str = "bebshax-client"
    jwt_algorithm: str = "HS256"
    # 1 day, not 7: there is no revocation list, so a leaked token is valid
    # until it expires. Chosen over jti-based revocation because that needs a
    # new table, a migration and a check on every request.
    jwt_expire_days: int = 1

    # Empty = federated Neon sign-in disabled; /api/auth/sync answers 503.
    # Never default to a live tenant URL — that silently binds every deploy
    # to one personal Neon project.
    neon_auth_url: str = ""

    require_email_verification: bool | None = None

    rate_limit_storage_uri: str | None = None
    rate_limit_trust_forwarded_for: bool = False

    @property
    def email_verification_enforced(self) -> bool:
        if self.require_email_verification is not None:
            return self.require_email_verification
        return self.environment in ("production", "staging") and bool(self.resend_api_key)

    @field_validator("jwt_secret")
    @classmethod
    def secret_must_be_real(cls, v: str) -> str:
        if not v or len(v) < 32:
            raise ValueError(
                "BEBSHAX_JWT_SECRET missing or <32 chars. Generate:\n"
                '  python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        if v == BURNED_JWT_SECRET:
            raise ValueError(
                "BEBSHAX_JWT_SECRET is the burned git-history value. "
                "Generate a new one — the old secret is permanently compromised."
            )
        return v

    @field_validator("resend_api_key")
    @classmethod
    def validate_resend_api_key(cls, v: str | None, info) -> str | None:
        env = info.data.get("environment", "development")
        if env in ("production", "staging") and not v:
            raise ValueError(
                "BEBSHAX_RESEND_API_KEY is required in production/staging environments. "
                "Register at resend.com and configure BEBSHAX_RESEND_API_KEY."
            )
        return v

    @field_validator("demo_mode")
    @classmethod
    def demo_mode_forbidden_in_hosted_envs(cls, v: bool, info) -> bool:
        env = info.data.get("environment", "development")
        if v and env in ("production", "staging"):
            raise ValueError(
                "BEBSHAX_DEMO_MODE=true seeds well-known demo credentials "
                "(founder@bebshax.ai) and must never run with "
                "BEBSHAX_ENVIRONMENT=production/staging. Unset BEBSHAX_DEMO_MODE, "
                "or keep the default development environment for the "
                "demo/exhibition profile (docs/DEMO.md \u00a77)."
            )
        return v

    @field_validator("email_from_address")
    @classmethod
    def email_from_required_in_hosted_envs(cls, v: str, info) -> str:
        env = info.data.get("environment", "development")
        if env in ("production", "staging") and not v.strip():
            raise ValueError(
                "BEBSHAX_EMAIL_FROM_ADDRESS is required in production/staging "
                "environments. Set it to a sender on a domain verified with your "
                "email provider (Resend refuses unverified domains)."
            )
        return v



@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=_PROJECT_ROOT / ".env")


def export_provider_credentials(env_file: Path = _PROJECT_ROOT / ".env") -> list[str]:
    """Expose provider credentials declared in .env (e.g. OPENROUTER_API_KEY) to
    the adapter layer, which reads os.environ by the catalog's key_env names.
    Settings only maps BEBSHAX_* keys, so without this a key that lives only in
    .env never configured its provider. Process variables always win."""
    if not env_file.is_file():
        return []
    from dotenv import dotenv_values

    exported: list[str] = []
    for name, value in dotenv_values(env_file).items():
        if not name or name.startswith(("BEBSHAX_", "VITE_")) or value is None or name in os.environ:
            continue
        os.environ[name] = value
        exported.append(name)
    return exported


def fail_fast_on_invalid_settings() -> Settings:
    """Refuse to boot with a missing/short/burned JWT secret or other invalid
    settings: a process that starts with them would mint forgeable tokens.
    Called from create_app(), never at import time (importing config must not
    read .env or construct Settings)."""
    try:
        return get_settings()
    except Exception as exc:  # pydantic ValidationError and friends
        print(f"\nFATAL: {exc}\n", file=sys.stderr)
        raise SystemExit(1) from None
