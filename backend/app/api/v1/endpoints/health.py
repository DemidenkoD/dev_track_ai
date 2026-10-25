"""GET /api/v1/health — unauthenticated Docker/Nginx/deployment probe.

Probes the real database with `SELECT 1` on every call (never hardcoded):
- database "connected" only when the probe succeeds, else "degraded".
- worker_status "active" only when the DB-backed job queue
  (`analysis_runs`) is readable, else "degraded" (degraded-safe default —
  the probe must never 500 even when Postgres is down).
"""

from fastapi import APIRouter
from sqlalchemy import text

from app.schemas.api_contracts import HealthResponse

router = APIRouter(tags=["health"])


class HealthExtendedResponse(HealthResponse):
    """Health shape plus boolean-only LLM signal (never leaks key values).

    ``HealthResponse`` itself stays frozen at the 4-key contract shape;
    this subclass (defined here in Track 1's endpoint module) adds the
    advisory ``gemini_configured`` / ``gemini_model`` fields for the live
    probe without mutating the shared contract schema.

    ``gemini_configured`` / ``gemini_model`` report *effective* LLM values
    for backward compatibility (when OPENCODE_KEY or GLM keys are present
    they reflect the effective configuration with ``configured=True``).
    ``llm_provider``, ``opencode_configured``, ``opencode_model``,
    ``opencode_custom_endpoint``, ``glm_configured``, ``glm_model``, and
    ``llm_base_url`` are additive, optional diagnostics (``llm_base_url``
    is a plain URL and never carries secrets; ``opencode_custom_endpoint``
    is a presence boolean — True only when ``OPENCODE_BASE_URL`` differs
    from the canonical ``https://opencode.ai/inference/openai/v1`` gateway —
    so a custom opencode-go gateway URL is never leaked verbatim).
    """

    gemini_configured: bool = False
    gemini_model: str = "gemma-4-31b-it"
    llm_provider: str = "gemini"
    opencode_configured: bool = False
    opencode_model: str = "muse-spark-1.3-contributor"
    opencode_custom_endpoint: bool = False
    glm_configured: bool = False
    glm_model: str = "glm-5.3-flash"
    llm_base_url: str = ""


_DEFAULT_GEMINI_MODEL = "gemma-4-31b-it"
_DEFAULT_OPENCODE_MODEL = "muse-spark-1.3-contributor"
_DEFAULT_GLM_MODEL = "glm-5.3-flash"
_DEFAULT_GLM_BASE_URL = "https://api.z.ai/api/paas/v4/"
_DEFAULT_OPENCODE_BASE_URL = "https://opencode.ai/inference/openai/v1"
_PLACEHOLDER_KEYS = frozenset(
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


def _gemini_status() -> tuple[bool, str]:
    """Return (effective_configured, effective_model) without leaking secrets.

    Kept for backward compatibility: both values honor GLM > OPENCODE >
    GEMINI precedence (when a higher-precedence key is configured they
    report that provider's model with configured=True). Prefer
    :func:`_llm_status` for the full provider breakdown.
    """
    configured, model, _provider, _opencode, _glm, _glm_model, _base = _llm_status()
    return configured, model


def _resolve_manual_llm(
    *,
    glm_key: str,
    zai_key: str,
    opencode_key: str,
    gemini_key: str,
    glm_model: str,
    opencode_model: str,
    gemini_model: str,
    glm_base_url: str,
    opencode_base_url: str = "",
    provider_choice: str,
    opencode_api_key: str = "",
) -> tuple[bool, str, str, bool, bool, str, str]:
    """Shared manual precedence: explicit pin honored, else GLM > OPENCODE > GEMINI.

    ``opencode_model`` is passed through verbatim (accepted gateway IDs:
    muse-spark-1.3-contributor, kimi-k2.6, glm-5.3-flash,
    opencode-go/kimi-k2.6, opencode-go/glm-5.3-flash,
    z-ai/glm-5.3-flash). ``opencode_base_url`` defaults to the canonical
    ``https://opencode.ai/inference/openai/v1`` gateway; a custom
    opencode-go gateway URL may override it. ``OPENCODE_API_KEY`` is the
    primary credential, ``OPENCODE_KEY`` is an alias — either non-placeholder
    value configures opencode.
    """
    glm_ok = (
        glm_key.strip().lower() not in _PLACEHOLDER_KEYS
        or zai_key.strip().lower() not in _PLACEHOLDER_KEYS
    )
    opencode_ok = (
        opencode_api_key.strip().lower() not in _PLACEHOLDER_KEYS
        or opencode_key.strip().lower() not in _PLACEHOLDER_KEYS
    )
    gemini_ok = gemini_key.strip().lower() not in _PLACEHOLDER_KEYS
    glm_model = glm_model or _DEFAULT_GLM_MODEL
    opencode_model = opencode_model or _DEFAULT_OPENCODE_MODEL
    gemini_model = gemini_model or _DEFAULT_GEMINI_MODEL
    glm_base_url = glm_base_url or _DEFAULT_GLM_BASE_URL
    opencode_base_url = (opencode_base_url or "").strip() or _DEFAULT_OPENCODE_BASE_URL
    choice = (provider_choice or "auto").strip().lower()
    if choice not in ("auto", "glm", "opencode", "gemini"):
        choice = "auto"
    if choice == "glm":
        return glm_ok, glm_model, "glm", opencode_ok, glm_ok, glm_model, glm_base_url
    if choice == "opencode":
        # Explicit opencode pin stays on the gateway even when GLM keys are
        # also present (no fall-through to direct GLM).
        return (
            opencode_ok,
            opencode_model,
            "opencode",
            opencode_ok,
            glm_ok,
            glm_model,
            opencode_base_url,
        )
    if choice == "gemini":
        return gemini_ok, gemini_model, "gemini", opencode_ok, glm_ok, glm_model, ""
    if glm_ok:
        return True, glm_model, "glm", opencode_ok, True, glm_model, glm_base_url
    if opencode_ok:
        return (
            True,
            opencode_model,
            "opencode",
            True,
            False,
            glm_model,
            opencode_base_url,
        )
    if gemini_ok:
        return True, gemini_model, "gemini", False, False, glm_model, ""
    return False, gemini_model, "unconfigured", False, False, glm_model, ""


def _llm_status() -> tuple[bool, str, str, bool, bool, str, str]:
    """Return (configured, model, provider, opencode_cfg, glm_cfg, glm_model, base_url).

    Booleans only — never leaks key values. Preferred path delegates to the
    Settings effective_* properties (GLM > OPENCODE > GEMINI in auto, explicit
    LLM_PROVIDER pins honored without silent fall-through).
    """
    try:
        from app.core.config import get_settings

        app_settings = get_settings()
        # Preferred path: Settings exposes the effective_* properties.
        provider_attr = getattr(app_settings, "effective_llm_provider", None)
        model_attr = getattr(app_settings, "effective_llm_model", None)
        effective_attr = getattr(app_settings, "effective_llm_configured", None)
        opencode_attr = getattr(app_settings, "opencode_configured", None)
        glm_attr = getattr(app_settings, "glm_configured", None)
        glm_model_attr = getattr(app_settings, "GLM_MODEL", None)
        base_url_attr = getattr(app_settings, "effective_llm_base_url", None)
        if (
            isinstance(provider_attr, str)
            and isinstance(model_attr, str)
            and isinstance(effective_attr, bool)
            and isinstance(opencode_attr, bool)
        ):
            glm_ok = bool(glm_attr) if isinstance(glm_attr, bool) else False
            glm_model_val = (
                str(glm_model_attr)
                if isinstance(glm_model_attr, str) and glm_model_attr
                else _DEFAULT_GLM_MODEL
            )
            base_url_val = (
                str(base_url_attr) if isinstance(base_url_attr, str) else ""
            )
            return (
                effective_attr,
                model_attr or _DEFAULT_GEMINI_MODEL,
                provider_attr,
                opencode_attr,
                glm_ok,
                glm_model_val,
                base_url_val,
            )
        # Legacy fallback: derive precedence manually (boolean-only, no logging).
        return _resolve_manual_llm(
            glm_key=str(getattr(app_settings, "GLM_API_KEY", "") or ""),
            zai_key=str(getattr(app_settings, "ZAI_API_KEY", "") or ""),
            opencode_key=str(getattr(app_settings, "OPENCODE_KEY", "") or ""),
            opencode_api_key=str(
                getattr(app_settings, "OPENCODE_API_KEY", "") or ""
            ),
            gemini_key=str(getattr(app_settings, "GEMINI_API_KEY", "") or ""),
            glm_model=str(
                getattr(app_settings, "GLM_MODEL", _DEFAULT_GLM_MODEL)
                or _DEFAULT_GLM_MODEL
            ),
            opencode_model=str(
                getattr(app_settings, "OPENCODE_MODEL", _DEFAULT_OPENCODE_MODEL)
                or _DEFAULT_OPENCODE_MODEL
            ),
            gemini_model=str(
                getattr(app_settings, "GEMINI_MODEL", _DEFAULT_GEMINI_MODEL)
                or _DEFAULT_GEMINI_MODEL
            ),
            glm_base_url=str(
                getattr(app_settings, "GLM_BASE_URL", _DEFAULT_GLM_BASE_URL)
                or _DEFAULT_GLM_BASE_URL
            ),
            opencode_base_url=str(
                getattr(
                    app_settings, "OPENCODE_BASE_URL", _DEFAULT_OPENCODE_BASE_URL
                )
                or _DEFAULT_OPENCODE_BASE_URL
            ),
            provider_choice=str(getattr(app_settings, "LLM_PROVIDER", "auto") or "auto"),
        )
    except Exception:
        import os

        return _resolve_manual_llm(
            glm_key=os.environ.get("GLM_API_KEY", ""),
            zai_key=os.environ.get("ZAI_API_KEY", ""),
            opencode_key=os.environ.get("OPENCODE_KEY", ""),
            opencode_api_key=os.environ.get("OPENCODE_API_KEY", ""),
            gemini_key=os.environ.get("GEMINI_API_KEY", ""),
            glm_model=(
                os.environ.get("GLM_MODEL", _DEFAULT_GLM_MODEL) or _DEFAULT_GLM_MODEL
            ),
            opencode_model=(
                os.environ.get("OPENCODE_MODEL", _DEFAULT_OPENCODE_MODEL)
                or _DEFAULT_OPENCODE_MODEL
            ),
            gemini_model=(
                os.environ.get("GEMINI_MODEL", _DEFAULT_GEMINI_MODEL)
                or _DEFAULT_GEMINI_MODEL
            ),
            glm_base_url=(
                os.environ.get("GLM_BASE_URL", _DEFAULT_GLM_BASE_URL)
                or _DEFAULT_GLM_BASE_URL
            ),
            opencode_base_url=os.environ.get(
                "OPENCODE_BASE_URL", _DEFAULT_OPENCODE_BASE_URL
            )
            or _DEFAULT_OPENCODE_BASE_URL,
            provider_choice=os.environ.get("LLM_PROVIDER", "auto"),
        )


def _opencode_gateway_status() -> tuple[str, bool]:
    """Return (opencode_model verbatim, custom_endpoint boolean).

    ``opencode_model`` is the effective ``OPENCODE_MODEL`` passed through
    verbatim (no validation) so gateway IDs such as ``kimi-k2.6``,
    ``glm-5.3-flash``, ``opencode-go/kimi-k2.6``,
    ``opencode-go/glm-5.3-flash``, or ``z-ai/glm-5.3-flash`` are reported
    exactly as configured. ``custom_endpoint`` is True only when
    ``OPENCODE_BASE_URL`` differs from the canonical
    ``https://opencode.ai/inference/openai/v1`` gateway (empty also means
    default, never custom); the URL value itself is never returned here —
    use ``llm_base_url`` for the plain-URL diagnostic.
    """
    try:
        from app.core.config import get_settings

        app_settings = get_settings()
        raw_model = getattr(
            app_settings, "OPENCODE_MODEL", _DEFAULT_OPENCODE_MODEL
        )
        model_val = (
            str(raw_model).strip()
            if isinstance(raw_model, str) and str(raw_model).strip()
            else _DEFAULT_OPENCODE_MODEL
        )
        raw_base = getattr(
            app_settings, "OPENCODE_BASE_URL", _DEFAULT_OPENCODE_BASE_URL
        )
        stripped = str(raw_base).strip() if isinstance(raw_base, str) else ""
        canonical = _DEFAULT_OPENCODE_BASE_URL.rstrip("/")
        custom = bool(stripped) and stripped.rstrip("/") != canonical
        return model_val, custom
    except Exception:
        import os

        model_val = (
            os.environ.get("OPENCODE_MODEL", _DEFAULT_OPENCODE_MODEL)
            or _DEFAULT_OPENCODE_MODEL
        )
        stripped = (os.environ.get("OPENCODE_BASE_URL", "") or "").strip()
        if not stripped:
            stripped = _DEFAULT_OPENCODE_BASE_URL
        custom = bool(stripped) and stripped.rstrip(
            "/"
        ) != _DEFAULT_OPENCODE_BASE_URL.rstrip("/")
        return model_val, custom


@router.get("/health", response_model=HealthExtendedResponse)
def health() -> HealthExtendedResponse:
    database = "degraded"
    worker_status = "degraded"
    try:
        from app.db.session import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "connected"
        # DB queue readable → worker dispatch path is reachable.
        try:
            from app.models.models import AnalysisRun

            with engine.connect() as conn:
                conn.execute(text(f"SELECT COUNT(*) FROM {AnalysisRun.__tablename__}"))
            worker_status = "active"
        except Exception as queue_exc:
            # Fresh database before startup seeding/migrations: the queue
            # table is absent but the dispatch path itself is reachable, so
            # the worker is idle-yet-alive ("active"). Any other queue error
            # stays a degraded-safe "degraded" (never 500s the probe).
            missing_table = (
                "no such table" in str(queue_exc).lower()
                or "undefined_table" in str(queue_exc).lower()
            )
            worker_status = "active" if missing_table else "degraded"
    except Exception:
        database = "degraded"
        worker_status = "degraded"
    gemini_configured, gemini_model, llm_provider, opencode_configured, glm_configured, glm_model, llm_base_url = _llm_status()
    opencode_model, opencode_custom_endpoint = _opencode_gateway_status()
    return HealthExtendedResponse(
        status="ok",
        version="0.3.0",
        database=database,
        worker_status=worker_status,
        gemini_configured=gemini_configured,
        gemini_model=gemini_model,
        llm_provider=llm_provider,
        opencode_configured=opencode_configured,
        opencode_model=opencode_model,
        opencode_custom_endpoint=opencode_custom_endpoint,
        glm_configured=glm_configured,
        glm_model=glm_model,
        llm_base_url=llm_base_url,
    )
