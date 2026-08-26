"""Environment-driven configuration. All BebshaX settings use the BEBSHAX_ prefix.

Provider API keys are intentionally NOT modeled here: freellmpool (Phase 3)
reads standard provider variables (GROQ_API_KEY, GEMINI_API_KEY, ...) directly,
so the provider list stays configuration-driven rather than hard-coded.
"""

from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BEBSHAX_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "BebshaX"
    environment: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    demo_mode: bool = False

    # M6: explicit origins — wildcard + allow_credentials is invalid per the
    # Fetch spec and unsafe. Comma-separated; override via BEBSHAX_CORS_ORIGINS.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # Consumed from Phase 6 (database); docker-compose pgvector service on 5433.
    database_url: str = "postgresql+asyncpg://bebshax:bebshax@localhost:5433/bebshax"

    # Phase 9: memory embedding backend — "local" (deterministic hash, offline)
    # or "freellmpool" (requires embedding_model pin; see docs/PERSONA_ENGINE.md)
    embedding_backend: str = "local"
    embedding_model: str | None = None

    # JWT Authentication settings (long-lived persistent login)
    jwt_secret: str = "bebshax-super-secret-jwt-signing-key-2026-auth-v1"
    jwt_expire_days: int = 365


@lru_cache
def get_settings() -> Settings:
    return Settings()
