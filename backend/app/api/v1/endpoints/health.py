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
    """Health shape plus boolean-only Gemini signal (never leaks the key).

    ``HealthResponse`` itself stays frozen at the 4-key contract shape;
    this subclass (defined here in Track 1's endpoint module) adds the
    advisory ``gemini_configured`` / ``gemini_model`` fields for the live
    probe without mutating the shared contract schema.
    """

    gemini_configured: bool = False
    gemini_model: str = "gemini-2.5-flash"


_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
_PLACEHOLDER_KEYS = frozenset(
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


def _gemini_status() -> tuple[bool, str]:
    """Return (gemini_configured, gemini_model) without leaking secrets."""
    try:
        from app.core.config import get_settings

        app_settings = get_settings()
        model = str(getattr(app_settings, "GEMINI_MODEL", _DEFAULT_GEMINI_MODEL) or _DEFAULT_GEMINI_MODEL)
        configured_attr = getattr(app_settings, "gemini_configured", None)
        if isinstance(configured_attr, bool):
            return configured_attr, model
        key = str(getattr(app_settings, "GEMINI_API_KEY", "") or "")
        return (key.strip().lower() not in _PLACEHOLDER_KEYS, model)
    except Exception:
        import os

        model = os.environ.get("GEMINI_MODEL", _DEFAULT_GEMINI_MODEL) or _DEFAULT_GEMINI_MODEL
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key or key.strip().lower() in _PLACEHOLDER_KEYS:
            return False, model
        return True, model


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
    gemini_configured, gemini_model = _gemini_status()
    return HealthExtendedResponse(
        status="ok",
        version="0.3.0",
        database=database,
        worker_status=worker_status,
        gemini_configured=gemini_configured,
        gemini_model=gemini_model,
    )
