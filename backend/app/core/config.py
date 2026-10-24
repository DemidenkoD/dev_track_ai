"""Application settings loaded from `.env` (template in `.env.example`).

Track 1 owns this file. Secrets (SECRET_KEY, GEMINI_API_KEY, MAIL_SMTP_PASS,
ADMIN_PASSWORD) must never be printed, logged, or committed.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Application ---
    APP_ENV: str = "development"
    APP_VERSION: str = "0.3.0"
    CORS_ORIGINS: str = "*"

    # --- Single predefined account (no registration endpoint exists) ---
    SECRET_KEY: str = "change-me-in-production-use-64-char-hex"
    ADMIN_USERNAME: str = "reviewer@datatalks.club"
    ADMIN_PASSWORD: str = "devtrack-zoomcamp-2026"
    # Kept in sync with TokenResponse.expires_in (86400s) and API contract.
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
