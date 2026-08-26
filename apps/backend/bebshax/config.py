"""Environment-driven configuration. BEBSHAX_ prefix for all settings."""
import sys
from functools import lru_cache
from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

BURNED_JWT_SECRET = "bebshax-super-secret-jwt-signing-key-2026-auth-v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BEBSHAX_", env_file=".env", extra="ignore"
    )

    app_name: str = "BebshaX"
    environment: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    demo_mode: bool = False
    database_url: str = (
        "postgresql+asyncpg://bebshax:bebshax@localhost:5433/bebshax"
    )
    embedding_backend: str = "local"
    embedding_model: str | None = None

    jwt_secret: str  # REQUIRED — no default
    jwt_secret_previous: str | None = None  # rotation grace window only
    jwt_issuer: str = "bebshax-api"
    jwt_audience: str = "bebshax-client"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 365

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
