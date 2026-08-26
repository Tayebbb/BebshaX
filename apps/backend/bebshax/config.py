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

    # M6: explicit origins — wildcard + allow_credentials is invalid per the
    # Fetch spec and unsafe. Comma-separated; override via BEBSHAX_CORS_ORIGINS.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"
    frontend_base_url: str = "http://localhost:5173"
    resend_api_key: str | None = None
    email_from_address: str = "noreply@bebshax.ai"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


    database_url: str = "postgresql+asyncpg://bebshax:bebshax@localhost:5433/bebshax"

    @property
    def sync_database_url(self) -> str:
        url = self.database_url
        if "+asyncpg" in url:
            return url.replace("+asyncpg", "")
        if "+aiosqlite" in url:
            return url.replace("+aiosqlite", "")
        return url

    # Phase 9: memory embedding backend — "local" (deterministic hash, offline)
    # or "freellmpool" (requires embedding_model pin; see docs/PERSONA_ENGINE.md)
    embedding_backend: str = "local"
    embedding_model: str | None = None

    jwt_secret: str  # REQUIRED — no default
    jwt_secret_previous: str | None = None  # rotation grace window only
    jwt_issuer: str = "bebshax-api"
    jwt_audience: str = "bebshax-client"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 365

    neon_auth_url: str = "https://ep-cold-star-azazjakq.neonauth.c-3.ap-southeast-1.aws.neon.tech/neondb/auth"

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


try:
    settings = Settings()
except Exception as e:
    print(f"\nFATAL: {e}\n", file=sys.stderr)
    raise SystemExit(1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
