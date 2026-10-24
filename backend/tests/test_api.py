"""Track 5: full API journey — login → project → milestones → analysis →
scorecard/evidence/diary/security/deployment → override.

Runs against an isolated in-memory SQLite database with stubbed auth, so no
Postgres, network, LLM, scanner, or worker side effects occur. Diary and
security correctly return 404 before the Track 3 worker produces snapshots;
those 404s are asserted as the expected pre-worker state. A worker-seeded
criterion assessment is inserted directly via the ORM (documented below) so
the override leg exercises the real PATCH handler end to end.

Skip-safe: missing Track 1 wiring yields pytest.skip with a reason.
"""

from __future__ import annotations

from uuid import UUID

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.unit]


@pytest.fixture()
def journey_client():
    """Isolated TestClient + session factory (same guarantees as invariants)."""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
    except ImportError as exc:
        pytest.skip(f"SQLAlchemy unavailable: {exc}")

    try:
        from app.db.base import Base
        from app.db.init_db import seed_builtin_rubric
        from app.main import app
        from app.core.deps import get_current_user, get_db
        from app.schemas.api_contracts import UserProfileSchema
    except Exception as exc:
        pytest.skip(f"Track 1 backend unavailable: {type(exc).__name__}: {exc}")

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    seed_db = TestingSession()
    try:
        seed_builtin_rubric(seed_db)
    finally:
        seed_db.close()

    def _override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    def _override_user():
        return UserProfileSchema(username="reviewer@datatalks.club", role="reviewer")

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    try:
        from app.api.v1.endpoints import analyses as analyses_mod

        analyses_mod.EPHEMERAL_NOTIFICATIONS.clear()
    except Exception:
        pass

    try:
        from fastapi.testclient import TestClient
    except ImportError as exc:
        pytest.skip(f"fastapi.testclient unavailable: {exc}")

    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, TestingSession
    finally:
        app.dependency_overrides.clear()
        try:
            from app.api.v1.endpoints import analyses as analyses_mod

            analyses_mod.EPHEMERAL_NOTIFICATIONS.clear()
        except Exception:
            pass


class TestFullApiJourney:
    def test_login_create_approve_analyze_modules_override(self, journey_client):
        client, Session = journey_client

        # 1. Login with the single predefined account (config defaults).
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "reviewer@datatalks.club", "password": "devtrack-zoomcamp-2026"},
        )
        assert resp.status_code == 200, resp.text[:300]
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

        # 2. Create a project (syntactic GitHub gate only — no network).
        resp = client.post(
            "/api/v1/projects",
            json={
                "name": "Journey Probe",
                "description": "Track 5 end-to-end probe.",
                "github_repo_url": "https://github.com/octocat/hello-world",
                "course_name": "AI Dev Tools Zoomcamp 2026",
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text[:300]
        project = resp.json()
        pid = project["id"]
        assert project["milestones_approved"] is False

        # 3. Approve milestones (draft → active gate).
        resp = client.post(
            f"/api/v1/projects/{pid}/milestones/approve",
            json={"approve_all": True},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["milestones_approved"] is True

        # 4. Trigger a manual analysis with a one-time notification address.
        resp = client.post(
            f"/api/v1/projects/{pid}/analyses",
            json={
                "notify_email_once": "journey-probe@example.com",
                "acknowledge_ephemeral_email": True,
            },
            headers=headers,
        )
        assert resp.status_code == 202, resp.text[:300]
        assert resp.json()["ephemeral_notification_queued"] is True
        assert "journey-probe@example.com" not in resp.text

        # 5a. Scorecard returns the advisory 12-criterion structure (worker
        # pending → empty assessments, disclaimer always present).
        resp = client.get(f"/api/v1/projects/{pid}/scorecard", headers=headers)
        assert resp.status_code == 200
        scorecard = resp.json()
        assert "advisory" in scorecard["advisory_disclaimer"].lower()
        assert isinstance(scorecard["criteria_assessments"], list)

        # 5b. Evidence explorer is reachable and filterable (empty pre-worker).
        resp = client.get(f"/api/v1/projects/{pid}/evidence", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []
        resp = client.get(
            f"/api/v1/projects/{pid}/evidence",
            params={"evidence_type": "commit"},
            headers=headers,
        )
        assert resp.status_code == 200

        # 5c. Diary + security correctly 404 before the worker runs.
        assert client.get(f"/api/v1/projects/{pid}/diary", headers=headers).status_code == 404
        assert client.get(f"/api/v1/projects/{pid}/security", headers=headers).status_code == 404

        # 5d. Deployment check records via the deterministic stub (no network).
        resp = client.post(
            f"/api/v1/projects/{pid}/deployments/check",
            json={"target_url": "https://example.com/"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text[:300]
        assert resp.json()["target_url"] == "https://example.com/"
        assert client.get(f"/api/v1/projects/{pid}/deployments", headers=headers).status_code == 200

        # 6. Simulate the worker seeding one criterion assessment, then
        # exercise the real human-override PATCH end to end.
        from app.models.models import CriterionAssessment
        from app.schemas.enums import ScoreState

        milestones = client.get(
            f"/api/v1/projects/{pid}/milestones", headers=headers
        ).json()["assessment_milestones"]
        run_id = client.get(f"/api/v1/projects/{pid}/analyses", headers=headers).json()[0]["id"]
        db = Session()
        try:
            assessment = CriterionAssessment(
                analysis_run_id=UUID(run_id),
                project_id=UUID(pid),
                assessment_milestone_id=UUID(milestones[0]["id"]),
                criterion_code=milestones[0].get("criterion_code", "ci_cd"),
                max_points=milestones[0].get("max_points", 2),
                ai_proposed_points=1,
                ai_reasoning="Journey probe reasoning.",
                ai_confidence=0.7,
                score_state=ScoreState.ESTIMATED,
                evidence_ids=[],
            )
            db.add(assessment)
            db.commit()
            assessment_id = str(assessment.id)
        finally:
            db.close()

        resp = client.patch(
            f"/api/v1/projects/{pid}/scorecard/{assessment_id}",
            json={
                "score_state": "verified",
                "human_override_points": 2,
                "human_override_reason": "Verified on a clean VM.",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text[:300]
        body = resp.json()
        assert body["ai_proposed_points"] == 1
        assert body["ai_reasoning"] == "Journey probe reasoning."
        assert body["human_override_points"] == 2
        assert body["overridden_at"] is not None
        assert body["effective_points"] == 2

        # Scorecard now reflects the verified override.
        scorecard = client.get(f"/api/v1/projects/{pid}/scorecard", headers=headers).json()
        assert any(
            c["human_override_points"] == 2 for c in scorecard["criteria_assessments"]
        )
