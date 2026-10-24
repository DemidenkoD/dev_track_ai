"""DevTrack AI FastAPI application entrypoint (Track 1).

Exposes `app` with all /api/v1 routers, CORS, version 0.3.0, and a startup
hook that creates tables + seeds the built-in Zoomcamp 2026 rubric.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.telemetry import instrument_app
from app.db.init_db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="DevTrack AI",
        description="Course-first AI project mentor (advisory, read-only).",
        version="0.3.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        # Intentional: wildcard origins ("*") cannot be combined with
        # credentials per the Fetch standard — and this API authenticates via
        # `Authorization: Bearer` headers, never cookies, so credentials stay
        # disabled. Do not set allow_credentials=True while origins is "*".
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router)
    instrument_app(application)

    @application.get("/", tags=["health"])
    def root() -> dict:
        return {"status": "ok", "version": "0.3.0"}

    return application


app = create_app()
