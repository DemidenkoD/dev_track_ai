"""Application settings loaded from `.env` (template in `.env.example`).

Track 1 owns this file. Secrets (SECRET_KEY, GEMINI_API_KEY, MAIL_SMTP_PASS,
ADMIN_PASSWORD) must never be printed, logged, or committed.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Placeholder Gemini keys are never treated as configured (mirrors
# backend/app/agents/base.py::is_gemini_configured + .env.example).
# Comparison is case-insensitive on the stripped value; the raw key value
# itself is never logged, printed, or included in errors/traces.
_PLACEHOLDER_GEMINI_KEYS: frozenset[str] = frozenset(
    {
        "",
        "your_gemini_api_key_here",
        "change-me",
        "changeme",
        "test",
        "dummy",
        "placeholder",
    }
)


def is_placeholder_gemini_key(value: str | None) -> bool:
    """True when the value is empty or a well-known dev/test placeholder."""
    if not value:
        return True
    return value.strip().lower() in _PLACEHOLDER_GEMINI_KEYS


def _resolve_env_files() -> list[str]:
    """Ordered dotenv search covering local and Docker runtimes.

    - Local ``pytest`` / ``uvicorn`` runs from the repo root rely on
      ``<repo>/.env`` (CWD may be repo root or ``backend/``).
    - Docker Compose sets ``WORKDIR /code`` with ``env_file: .env``
      resolving to ``/code/.env`` (usually absent) while secrets arrive
      via ``environment:`` — real env vars always win over dotenv files
      in pydantic-settings, so listing extra paths is safe.

    Missing files are ignored by pydantic-settings; later files override
    earlier ones, real process environment overrides all of them.
    """
    here = Path(__file__).resolve()
    try:
        backend_dir = here.parents[2]  # .../backend
        repo_root = here.parents[3]  # repo root containing docs/, backend/
    except IndexError:  # pragma: no cover - extremely shallow checkout
        backend_dir = here.parent
        repo_root = here.parent
    candidates: list[Path] = [
        Path("/code/.env"),
        backend_dir / ".env",
        repo_root / ".env",
        Path.cwd() / ".env",
        Path(".env"),
    ]
    seen: set[str] = set()
    resolved: list[str] = []
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            resolved.append(key)
    return resolved


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_resolve_env_files(), extra="ignore")

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
    def gemini_configured(self) -> bool:
        """Boolean-only Gemini signal (never exposes the key value)."""
        return not is_placeholder_gemini_key(self.GEMINI_API_KEY)

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


# Canonical singleton for Track 2 runtime agents:
# ``from app.core.config import settings`` always works (e.g. Docker
# WORKDIR=/code, local pytest from repo root, uvicorn from backend/).
# Backwards compatible: ``get_settings()`` remains the canonical accessor
# and returns this same cached instance. Never logs secret values.
settings = get_settings()
