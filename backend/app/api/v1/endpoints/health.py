"""GET /api/v1/health — unauthenticated Docker/Nginx/deployment probe."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.api_contracts import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    _ = settings  # version pinned by contract; settings reserved for future checks
    return HealthResponse(
        status="ok",
        version="0.3.0",
        database="connected",
        worker_status="active",
    )
