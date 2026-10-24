"""Aggregated /api/v1 router (API_CONTRACT §§1–8)."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    analyses,
    auth,
    evidence,
    health,
    milestones,
    modules,
    oncall,
    projects,
    rubrics,
    scorecard,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(rubrics.router)
api_router.include_router(projects.dashboard_router)
api_router.include_router(projects.router)
api_router.include_router(milestones.router)
api_router.include_router(analyses.router)
api_router.include_router(scorecard.router)
api_router.include_router(evidence.router)
api_router.include_router(modules.router)
api_router.include_router(oncall.router)
