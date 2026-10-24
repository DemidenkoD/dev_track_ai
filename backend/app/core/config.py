"""Application settings loaded from `.env` (template in `.env.example`).

Track 1 owns this file. Secrets (SECRET_KEY, GEMINI_API_KEY, MAIL_SMTP_PASS,
ADMIN_PASSWORD) must never be printed, logged, or committed.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Application ---
    APP_ENV: str = "development"
    APP_VERSION: str = "0.3.0"
    # Wildcard origin is intentional for a bearer-token API consumed by any
    # frontend origin; it MUST stay paired with allow_credentials=False in
    # main.py (browsers reject `Access-Control-Allow-Origin: *` when
    # credentials are included, and we use Authorization headers, not cookies).
    CORS_ORIGINS: str = "*"

    # --- Single predefined account (no registration endpoint exists) ---
    # Dev-only default so `pytest`/local boot works without secrets. The
    # production guard below refuses to start with this placeholder.
    SECRET_KEY: str = "change-me-in-production-use-64-char-hex"
    ADMIN_USERNAME: str = "reviewer@datatalks.club"
    ADMIN_PASSWORD: str = "devtrack-zoomcamp-2026"
    # 1440 min = 86400 s. Kept in sync with TokenResponse.expires_in and the
    # API contract (`POST /api/v1/auth/login` documents expires_in 86400).
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # --- Database (PostgreSQL in Docker; SQLite fallback for local boot) ---
    DATABASE_URL: str = "sqlite:///./devtrack_ai.db"

    # --- Gemini LLM (consumed by Track 2 runtime agents, not here) ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # --- GitHub (optional token for higher public rate limits) ---
    GITHUB_TOKEN: str = ""

    # --- One-time email notifications (in-memory only, never persisted) ---
    MAIL_SMTP_HOST: str = "smtp.example.com"
    MAIL_SMTP_PORT: int = 465
    MAIL_SMTP_SECURE: bool = True
    MAIL_SMTP_USER: str = ""
    MAIL_SMTP_PASS: str = ""
    MAIL_FROM: str = "DevTrack AI <user@example.com>"
    MAIL_BASE_URL: str = "http://localhost:8000"

    # --- Worker & resource limits ---
    WORKER_POLL_INTERVAL_SECONDS: int = 5
    ANALYSIS_TIMEOUT_SECONDS: int = 300
    MAX_REPO_SIZE_MB: int = 250

    @property
    def access_token_expire_seconds(self) -> int:
        return self.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _enforce_prod_secrets(self) -> "Settings":
        """Refuse the dev placeholder SECRET_KEY in production.

        Tests/local boot run with APP_ENV != production and are unaffected.
        """
        if self.APP_ENV.lower() == "production" and self.SECRET_KEY in (
            "",
            "change-me-in-production-use-64-char-hex",
        ):
            raise ValueError(
                "SECRET_KEY must be provided via the environment in production "
                "(no default is safe to ship)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
