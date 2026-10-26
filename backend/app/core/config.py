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
        "your_glm_key_here",
        "your_zai_key_here",
        "your_opencode_api_key_here",
        "your_opencode_key_here",
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
    GEMINI_MODEL: str = "gemma-4-31b-it"

    # --- OpenCode / Muse Spark (takes precedence over Gemini when present) ---
    # Canonical inference gateway: https://opencode.ai/inference/openai/v1
    # (OpenAI-compatible `client.chat.completions.create(...)`; see task spec).
    # OPENCODE_API_KEY is the primary credential; OPENCODE_KEY is kept as an
    # alias — either non-placeholder value configures opencode
    # (effective key = OPENCODE_API_KEY or OPENCODE_KEY). When configured it
    # takes precedence over GEMINI_API_KEY via the effective_llm_* properties
    # below. The raw key value must never be logged, printed, or included in
    # errors. Real gateway keys start with `oc_sk_...`; only empty/known
    # placeholder strings count as unconfigured (never prefix-match `oc_sk`).
    # OPENCODE_MODEL accepts gateway model IDs passed through verbatim (no
    # validation): muse-spark-1.3-contributor (default), kimi-k2.6,
    # glm-5.3-flash, and fully-qualified forms like opencode-go/kimi-k2.6,
    # opencode-go/glm-5.3-flash or z-ai/glm-5.3-flash when the gateway
    # requires a provider prefix.
    OPENCODE_API_KEY: str = ""
    OPENCODE_KEY: str = ""
    OPENCODE_MODEL: str = "muse-spark-1.3-contributor"
    # Canonical default gateway; override via env for a custom opencode-go
    # gateway endpoint. Plain URL only — never holds secrets, and never log
    # key material alongside it.
    OPENCODE_BASE_URL: str = "https://opencode.ai/inference/openai/v1"

    # --- Zhipu GLM (OpenAI-compatible, precedence over OpenCode in auto mode) ---
    # GLM_API_KEY is primary; ZAI_API_KEY is accepted as an alias for the same
    # credential (auth `Authorization: Bearer <key>` against GLM_BASE_URL).
    # Recommended generation defaults (temperature 1, top_p 0.95) are applied
    # by callers, not stored here. Raw key values must never be logged.
    GLM_API_KEY: str = ""
    ZAI_API_KEY: str = ""
    GLM_MODEL: str = "glm-5.3-flash"
    GLM_BASE_URL: str = "https://api.z.ai/api/paas/v4/"
    # Explicit provider pin: auto|glm|opencode|gemini (case-insensitive).
    # Explicit glm/opencode/gemini is honored even when its key is missing
    # (reports degraded/unconfigured, never silently falls through); auto
    # resolves GLM > OPENCODE > GEMINI.
    LLM_PROVIDER: str = "auto"

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

    @property
    def smtp_configured(self) -> bool:
        """Boolean-only SMTP readiness signal (never exposes secrets).

        False when the host is still the ``smtp.example.com`` placeholder
        (or empty) or when auth credentials are missing. Callers must treat
        a staged ephemeral notification as "queued in this process memory,
        not delivered" whenever this is False — the worker send will fail.
        """
        host = (self.MAIL_SMTP_HOST or "").strip().lower()
        if host in ("", "smtp.example.com"):
            return False
        if not (self.MAIL_SMTP_USER or "").strip():
            return False
        if not (self.MAIL_SMTP_PASS or "").strip():
            return False
        return True

    @property
    def smtp_config_warning(self) -> str | None:
        """Human-readable reason SMTP is unusable, or None when configured.

        Contains no secret values — only which category is missing so the
        API layer can log a safe warning at trigger time.
        """
        host = (self.MAIL_SMTP_HOST or "").strip()
        if host.lower() in ("", "smtp.example.com"):
            return (
                "MAIL_SMTP_HOST is still the placeholder "
                "(smtp.example.com); delivery will fail."
            )
        if not (self.MAIL_SMTP_USER or "").strip():
            return "MAIL_SMTP_USER is empty; SMTP auth will fail."
        if not (self.MAIL_SMTP_PASS or "").strip():
            return "MAIL_SMTP_PASS is empty; SMTP auth will fail."
        return None

    # --- Worker & resource limits ---
    WORKER_POLL_INTERVAL_SECONDS: int = 5
    ANALYSIS_TIMEOUT_SECONDS: int = 300
    MAX_REPO_SIZE_MB: int = 250

    # --- Phase 4 on-call Alertmanager webhook shared secret ---
    # The POST /api/v1/oncall/webhook endpoint authenticates via
    # `Authorization: Bearer <ALERTMANAGER_WEBHOOK_SECRET>` or the
    # `X-Alertmanager-Secret` header (no user JWT). The raw value is
    # never logged, printed, or included in errors/traces — only a
    # boolean mismatch (401) is observable.
    # Fail-closed default: must be set in .env, never commit.
    ALERTMANAGER_WEBHOOK_SECRET: str = ""

    @property
    def access_token_expire_seconds(self) -> int:
        return self.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    @property
    def gemini_configured(self) -> bool:
        """Boolean-only Gemini signal (never exposes the key value)."""
        return not is_placeholder_gemini_key(self.GEMINI_API_KEY)

    @property
    def opencode_configured(self) -> bool:
        """Boolean-only OpenCode signal (never exposes the key value).

        OPENCODE_API_KEY is primary, OPENCODE_KEY is an alias — either
        non-placeholder value configures opencode.
        """
        return not is_placeholder_gemini_key(self._opencode_effective_key)

    @property
    def glm_configured(self) -> bool:
        """Boolean-only GLM signal (GLM_API_KEY or ZAI_API_KEY alias)."""
        return not is_placeholder_gemini_key(
            self.GLM_API_KEY
        ) or not is_placeholder_gemini_key(self.ZAI_API_KEY)

    @property
    def _opencode_effective_key(self) -> str:
        """OPENCODE_API_KEY primary, OPENCODE_KEY alias (never log this)."""
        if not is_placeholder_gemini_key(self.OPENCODE_API_KEY):
            return self.OPENCODE_API_KEY
        return self.OPENCODE_KEY

    @property
    def _glm_effective_key(self) -> str:
        """GLM_API_KEY primary, ZAI_API_KEY alias (never log this)."""
        if not is_placeholder_gemini_key(self.GLM_API_KEY):
            return self.GLM_API_KEY
        return self.ZAI_API_KEY

    @property
    def _llm_provider_choice(self) -> str:
        """Normalized LLM_PROVIDER pin (auto|glm|opencode|gemini)."""
        choice = (self.LLM_PROVIDER or "auto").strip().lower()
        if choice in ("auto", "glm", "opencode", "gemini"):
            return choice
        return "auto"

    @property
    def effective_llm_configured(self) -> bool:
        """True when the resolved provider holds a real key (boolean only).

        Explicit LLM_PROVIDER pins never fall through: a missing key for the
        pinned provider reports False (degraded/unconfigured). Auto resolves
        GLM > OPENCODE > GEMINI.
        """
        choice = self._llm_provider_choice
        if choice == "glm":
            return self.glm_configured
        if choice == "opencode":
            return self.opencode_configured
        if choice == "gemini":
            return self.gemini_configured
        return self.glm_configured or self.opencode_configured or self.gemini_configured

    @property
    def effective_llm_provider(self) -> str:
        """Resolved provider: explicit pin honored, else GLM > OPENCODE > GEMINI.

        Returns 'unconfigured' in auto mode when no key is present.
        """
        choice = self._llm_provider_choice
        if choice in ("glm", "opencode", "gemini"):
            return choice
        if self.glm_configured:
            return "glm"
        if self.opencode_configured:
            return "opencode"
        if self.gemini_configured:
            return "gemini"
        return "unconfigured"

    @property
    def effective_llm_model(self) -> str:
        """Model for the resolved provider (explicit pin honored, else auto)."""
        choice = self._llm_provider_choice
        if choice == "glm":
            return self.GLM_MODEL or "glm-5.3-flash"
        if choice == "opencode":
            return self.OPENCODE_MODEL
        if choice == "gemini":
            return self.GEMINI_MODEL
        if self.glm_configured:
            return self.GLM_MODEL or "glm-5.3-flash"
        if self.opencode_configured:
            return self.OPENCODE_MODEL
        return self.GEMINI_MODEL

    @property
    def effective_llm_api_key(self) -> str:
        """Effective key honoring GLM > OPENCODE > GEMINI (never log this).

        Explicit LLM_PROVIDER pins never fall through to another provider's
        key; auto resolves GLM > OPENCODE > GEMINI.
        """
        choice = self._llm_provider_choice
        if choice == "glm":
            return self._glm_effective_key
        if choice == "opencode":
            return self._opencode_effective_key
        if choice == "gemini":
            return self.GEMINI_API_KEY
        if self.glm_configured:
            return self._glm_effective_key
        if self.opencode_configured:
            return self._opencode_effective_key
        return self.GEMINI_API_KEY

    @property
    def effective_llm_base_url(self) -> str:
        """Base URL for the resolved provider (plain URL, never holds secrets).

        - provider ``glm`` → ``GLM_BASE_URL`` (direct Z.AI default).
        - provider ``opencode`` → ``OPENCODE_BASE_URL`` (canonical
          ``https://opencode.ai/inference/openai/v1`` default; a custom URL
          may override it for an opencode-go gateway).
        - other providers return "".
        """
        if self.effective_llm_provider == "glm":
            return self.GLM_BASE_URL or "https://api.z.ai/api/paas/v4/"
        if self.effective_llm_provider == "opencode":
            return (
                self.OPENCODE_BASE_URL
                or "https://opencode.ai/inference/openai/v1"
            )
        return ""

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
