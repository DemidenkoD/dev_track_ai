"""Engine + session factory built from DATABASE_URL.

PostgreSQL (`postgresql+psycopg://...`) in Docker/production; SQLite fallback
for local boot and tests (dependency-overridable via `get_db`).

If the configured driver (e.g. psycopg) is not installed, falls back to a
local SQLite file with a warning so `app.main:app` still boots outside
Docker. Docker images (Track 6) install psycopg and use PostgreSQL.
"""

import importlib
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

DATABASE_URL = settings.DATABASE_URL

_DRIVER_MODULES = {
    "psycopg": "psycopg",
    "psycopg2": "psycopg2",
    "pg8000": "pg8000",
    "asyncpg": "asyncpg",
}


def _driver_available(url: str) -> bool:
    """Check the DBAPI driver for a SQLAlchemy URL is importable."""
    driver = url.split("://")[0].split("+")
    module = _DRIVER_MODULES.get(driver[-1] if len(driver) > 1 else "", "")
    if not module:
        return True  # e.g. sqlite / unknown: let create_engine decide
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False


if not _driver_available(DATABASE_URL):
    logger.warning(
        "DB driver for %s not installed; falling back to local SQLite",
        DATABASE_URL.split("@")[-1],
    )
    DATABASE_URL = "sqlite:///./devtrack_ai.db"

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args=(
        {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    ),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
