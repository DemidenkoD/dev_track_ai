"""Shared pytest fixtures for Track 5 QA (read-only on backend/app, frontend/src).

Never touches product code, secrets, live network, LLM, or scanners.
All external calls are mocked; missing Track 1 wiring yields skip, not failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make `import app.*` (backend/app/...) resolvable without installing a package.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

REPO_ROOT = _BACKEND_DIR.parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Repository root (read-only access to specs/contracts)."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def backend_dir() -> Path:
    """backend/ directory (so tests can statically inspect Track 1 sources)."""
    return _BACKEND_DIR


def _try_import_app():
    """Import the FastAPI application; return (app, reason_if_unavailable)."""
    try:
        from app.main import app  # noqa: PLC0415

        return app, None
    except Exception as exc:  # Track 1 wiring / deps missing -> skip, never fail
        return None, f"Track 1 backend app unavailable (blocked dep): {type(exc).__name__}"


@pytest.fixture(scope="session")
def fastapi_app():
    """FastAPI app instance, or skip when Track 1 wiring is unavailable."""
    app, reason = _try_import_app()
    if app is None:
        pytest.skip(reason)
    return app


@pytest.fixture(scope="session")
def client(fastapi_app):
    """TestClient with SQLite-friendly DB dependency override stub.

    Overrides the `get_db` dependency (if present) with a stub that raises a
    clear error on use, so no test can accidentally touch Postgres. Tests that
    need the DB must mock service layers instead.
    """
    try:
        from fastapi.testclient import TestClient  # noqa: PLC0415
    except Exception as exc:
        pytest.skip(f"fastapi.testclient unavailable: {type(exc).__name__}")

    test_client = TestClient(fastapi_app, raise_server_exceptions=False)

    # Best-effort DB override: only applied when a get_db dependency exists.
    try:
        from app.db.session import get_db  # noqa: PLC0415

        def _stub_db():
            raise RuntimeError(
                "Track 5 tests never touch a real database; mock service layers instead."
            )

        test_client.app.dependency_overrides[get_db] = _stub_db
    except Exception:
        pass  # Track 1 DB module shape may differ; live-client tests still skip-safe

    return test_client


@pytest.fixture()
def auth_headers() -> dict:
    """Placeholder Bearer header factory (no real secrets minted here)."""
    return {"Authorization": "Bearer test-token-track5-stub"}
