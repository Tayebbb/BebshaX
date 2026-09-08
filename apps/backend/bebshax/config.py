import os
import sys
from pathlib import Path
from functools import lru_cache
from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


for p in (".env", "../.env", "../../.env"):
    if os.path.exists(p):
        load_dotenv(p)
        break

BURNED_JWT_SECRET = "bebshax-super-secret-jwt-signing-key-2026-auth-v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BEBSHAX_", env_file=(".env", "../.env", "../../.env"), extra="ignore"
    )


    app_name: str = "BebshaX"
    environment: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    demo_mode: bool = False
    log_level: str = "INFO"

    # Filesystem roots for uploaded/processed datasets. Relative paths resolve
    # against the process CWD (dev: repo root -> data/). Containers set
    # BEBSHAX_DATA_DIR to a writable, volume-backed absolute path.
    data_dir: str = "data"
    upload_dir: str | None = None  # default: <data_dir>/uploads
    processed_dir: str | None = None  # default: <data_dir>/processed
    ml_persona_artifact_dir: str | None = None

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

    # Phase 9: memory embedding backend — "local" (deterministic hash, offline),
    # "auto" (probe Ollama on first use, semantic embeddings when the embed
    # model is pulled, hash fallback otherwise), or "freellmpool" (requires
    # embedding_model pin; see docs/PERSONA_ENGINE.md). Default stays "local",
    # NOT "auto": auto can resolve to a different space across restarts
    # (daemon up vs down), stranding earlier vectors behind the space filter —
    # determinism beats semantics for the default. Opt into "auto" per deploy.
    embedding_backend: str = "local"
    embedding_model: str | None = None

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



try:
    settings = Settings()
except Exception as e:
    print(f"\nFATAL: {e}\n", file=sys.stderr)
    raise SystemExit(1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
