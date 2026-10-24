"""Track 5: health + auth contract tests (API_CONTRACT.md Section 1).

GET /api/v1/health shape {status, version, database, worker_status};
POST /api/v1/auth/login validation; GET /api/v1/auth/me requires Bearer.

All live-client tests skip gracefully when Track 1 wiring is unavailable.
Schema-shape tests run fully mocked with no network/secrets/DB.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.unit]


def _import_or_skip(module: str, name: str | None = None):
    try:
        mod = pytest.importorskip(module, reason=f"Blocked on Track 1 dep: {module} unavailable")
        return getattr(mod, name) if name else mod
    except pytest.skip.Exception:
        raise


class TestHealthEndpoint:
    def test_health_response_shape_live(self, client):
        """Live: GET /api/v1/health returns the frozen 4-key shape."""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200, f"unexpected status: {resp.status_code} {resp.text[:300]}"
        body = resp.json()
        assert body["status"] == "ok"
        assert body["version"] == "0.3.0"
        assert body["database"] == "connected"
        assert body["worker_status"] == "active"

    def test_health_schema_defaults_mocked(self):
        """Mocked: HealthResponse carries the contract defaults (no app boot)."""
        HealthResponse = _import_or_skip("app.schemas.api_contracts", "HealthResponse")
        payload = HealthResponse().model_dump()
        assert payload == {
            "status": "ok",
            "version": "0.3.0",
            "database": "connected",
            "worker_status": "active",
        }

    def test_root_probe_shape_live(self, client):
        """Live: GET / returns the minimal {status, version} probe."""
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["version"] == "0.3.0"


class TestAuthContract:
    def test_login_rejects_bad_credentials_live(self, client):
        """Live: wrong password -> 401, never leaks which field was wrong."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "reviewer@datatalks.club", "password": "wrong-password"},
        )
        assert resp.status_code == 401

    def test_login_validation_errors_live(self, client):
        """Live: missing fields -> 422 (FastAPI request validation)."""
        resp = client.post("/api/v1/auth/login", json={"username": "reviewer@datatalks.club"})
        assert resp.status_code == 422

    def test_me_requires_bearer_live(self, client):
        """Live: GET /api/v1/auth/me without token -> 401/403, never 200."""
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code in (401, 403)

    def test_me_rejects_garbage_bearer_live(self, client):
        """Live: garbage token -> 401, never 200."""
        resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 401

    def test_login_request_schema_mocked(self):
        """Mocked: LoginRequest requires username + password (no secrets used)."""
        LoginRequest = _import_or_skip("app.schemas.api_contracts", "LoginRequest")
        with pytest.raises(Exception):
            LoginRequest(username="reviewer@datatalks.club")

    def test_token_response_shape_mocked(self):
        """Mocked: TokenResponse shape is {access_token, token_type, expires_in, user}."""
        TokenResponse = _import_or_skip("app.schemas.api_contracts", "TokenResponse")
        token = TokenResponse(
            access_token="stub",
            user={"username": "reviewer@datatalks.club", "role": "reviewer"},
        )
        assert token.token_type == "bearer"
        assert token.expires_in == 86400
        assert token.user.role == "reviewer"

    def test_no_public_registration_route_live(self, client):
        """Live: no public signup/register endpoint may exist (single account invariant)."""
        for path in (
            "/api/v1/auth/register",
            "/api/v1/auth/signup",
            "/api/v1/users",
        ):
            resp = client.post(path, json={})
            assert resp.status_code == 404, f"unexpected route exists: {path}"
