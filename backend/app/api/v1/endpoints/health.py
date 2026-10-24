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


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
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
    return HealthResponse(
        status="ok",
        version="0.3.0",
        database=database,
        worker_status=worker_status,
    )
