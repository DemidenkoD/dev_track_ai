"""Track 5: Phase 4b On-Call History tab (webhook -> incidents -> acknowledge).

Covers (docs/specs/API_CONTRACT.md §8, backend/app/api/v1/endpoints/oncall.py):

  1. POST /api/v1/oncall/webhook is 401 without/wrong shared secret, 202 with
     a valid secret and persists an incident row.
  2. Re-POST of the same (fingerprint, startsAt) updates the existing row
     (dedupe) instead of inserting a duplicate.
  3. Payload redaction: raw email / JWT / Bearer values are absent from the
     persisted detail; redaction markers are present; nothing leaks to logs.
  4. GET /api/v1/oncall/incidents supports ?status= + ?limit=.
  5. GET /api/v1/oncall/incidents/{id} carries a diagnosis with
     read_only_verified=True and a non-empty recommended_actions plan.
  6. POST /api/v1/oncall/incidents/{id}/acknowledge sets acknowledged + note.
  7. POST /api/v1/oncall/diagnose still returns 200 (no regression).
  8. Guard rails: zero email column on OnCallIncident, agent has no
     shell/subprocess/DB-write, and the on-call flow never touches
     ai_proposed_points / ai_reasoning / score_state (dev completion and
     assessment scores stay decoupled).

Uses the shared `isolated_client` + `repo_root` fixtures from
backend/tests/conftest.py (throwaway SQLite + seeded rubric, stub auth).
Never touches Postgres, the network, LLM, or scanners.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.unit]

_TEST_SECRET = "track5-qa-webhook-secret"

_FIRING_STARTS_AT = "2026-10-26T10:00:00.000Z"


def _set_webhook_secret(monkeypatch) -> str:
    """Point the cached settings singleton at a known webhook secret."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(
        settings, "ALERTMANAGER_WEBHOOK_SECRET", _TEST_SECRET, raising=False
    )
    return _TEST_SECRET


def _auth_headers(secret: str | None) -> dict:
    if secret is None:
        return {}
    return {"Authorization": f"Bearer {secret}"}


def _webhook_payload(
    fingerprint: str = "fp-track5-001",
    starts_at: str = _FIRING_STARTS_AT,
    status: str = "firing",
    alertname: str = "HighHttp5xxErrorRate",
    severity: str = "critical",
    service: str = "api",
    description: str = "5xx spike on /api/v1/projects",
) -> dict:
    return {
        "receiver": "devtrack-oncall",
        "status": status,
        "alerts": [
            {
                "status": status,
                "labels": {
                    "alertname": alertname,
                    "severity": severity,
                    "service": service,
                },
                "annotations": {
                    "summary": "5xx spike",
                    "description": description,
                },
                "startsAt": starts_at,
                "endsAt": None,
                "fingerprint": fingerprint,
            }
        ],
    }


def _post_webhook(client, payload: dict, secret: str | None) -> object:
    return client.post(
        "/api/v1/oncall/webhook", json=payload, headers=_auth_headers(secret)
    )


# ---------------------------------------------------------------------------
# 1. Webhook auth gate: 401 without/wrong secret, 202 with secret
# ---------------------------------------------------------------------------
class TestWebhookAuthGate:
    def test_webhook_401_without_secret(self, isolated_client, monkeypatch):
        _set_webhook_secret(monkeypatch)
        client, _ = isolated_client
        resp = _post_webhook(client, _webhook_payload(), None)
        assert resp.status_code == 401, resp.text[:300]

    def test_webhook_401_with_wrong_secret(self, isolated_client, monkeypatch):
        _set_webhook_secret(monkeypatch)
        client, _ = isolated_client
        resp = _post_webhook(client, _webhook_payload(), "wrong-secret")
        assert resp.status_code == 401, resp.text[:300]

    def test_webhook_202_with_secret_creates_incident(
        self, isolated_client, monkeypatch
    ):
        secret = _set_webhook_secret(monkeypatch)
        client, _ = isolated_client
        resp = _post_webhook(client, _webhook_payload(), secret)
        assert resp.status_code == 202, resp.text[:300]
        body = resp.json()
        assert len(body["incidents"]) == 1
        inc = body["incidents"][0]
        assert inc["alert_name"] == "HighHttp5xxErrorRate"
        assert inc["severity"] == "critical"
        assert inc["service"] == "api"
        assert inc["status"] == "firing"
        assert inc["fingerprint"] == "fp-track5-001"
        assert inc["read_only_verified"] is True

    def test_webhook_accepts_x_alertmanager_secret_header(
        self, isolated_client, monkeypatch
    ):
        secret = _set_webhook_secret(monkeypatch)
        client, _ = isolated_client
        resp = client.post(
            "/api/v1/oncall/webhook",
            json=_webhook_payload(fingerprint="fp-track5-header"),
            headers={"X-Alertmanager-Secret": secret},
        )
        assert resp.status_code == 202, resp.text[:300]


# ---------------------------------------------------------------------------
# 1b. Fail-closed defaults: empty/placeholder secrets never authenticate
# ---------------------------------------------------------------------------
class TestWebhookFailClosedDefaults:
    def test_shipped_default_is_empty_fail_closed(self):
        """The committed default must be "" (fail-closed, never a real secret)."""
        try:
            from app.core.config import Settings
        except ImportError as exc:
            pytest.skip(f"app.core.config unavailable: {exc}")

        default = Settings.model_fields["ALERTMANAGER_WEBHOOK_SECRET"].default
        assert default == "", f"fail-closed default changed: {default!r}"

    def test_empty_configured_secret_rejects_everything(
        self, isolated_client, monkeypatch
    ):
        """Default-equivalent empty secret → 401 with or without a header."""
        from app.core.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(
            settings, "ALERTMANAGER_WEBHOOK_SECRET", "", raising=False
        )
        client, _ = isolated_client
        assert (
            _post_webhook(client, _webhook_payload(), "anything-at-all").status_code
            == 401
        )
        assert _post_webhook(client, _webhook_payload(), None).status_code == 401

    def test_placeholder_changeme_dev_only_rejects(
        self, isolated_client, monkeypatch
    ):
        """Placeholder 'changeme-dev-only' never authenticates, even on match."""
        from app.core.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(
            settings,
            "ALERTMANAGER_WEBHOOK_SECRET",
            "changeme-dev-only",
            raising=False,
        )
        client, _ = isolated_client
        resp = _post_webhook(client, _webhook_payload(), "changeme-dev-only")
        assert resp.status_code == 401, resp.text[:300]

    def test_placeholder_change_me_alertmanager_secret_rejects(
        self, isolated_client, monkeypatch
    ):
        """Placeholder 'change-me-alertmanager-secret' never authenticates."""
        from app.core.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(
            settings,
            "ALERTMANAGER_WEBHOOK_SECRET",
            "change-me-alertmanager-secret",
            raising=False,
        )
        client, _ = isolated_client
        resp = _post_webhook(
            client, _webhook_payload(), "change-me-alertmanager-secret"
        )
        assert resp.status_code == 401, resp.text[:300]


# ---------------------------------------------------------------------------
# 2. Dedupe: same (fingerprint, startsAt) updates, never duplicates
# ---------------------------------------------------------------------------
class TestWebhookDedupe:
    def test_same_fingerprint_and_starts_at_updates_not_duplicates(
        self, isolated_client, monkeypatch
    ):
        secret = _set_webhook_secret(monkeypatch)
        client, _ = isolated_client
        first = _post_webhook(
            client,
            _webhook_payload(
                fingerprint="fp-track5-dedupe", status="firing"
            ),
            secret,
        )
        assert first.status_code == 202, first.text[:300]
        first_id = first.json()["incidents"][0]["id"]

        second = _post_webhook(
            client,
            _webhook_payload(
                fingerprint="fp-track5-dedupe",
                status="resolved",
                # same startsAt on purpose
            ),
            secret,
        )
        assert second.status_code == 202, second.text[:300]
        assert second.json()["incidents"][0]["id"] == first_id
        assert second.json()["incidents"][0]["status"] == "resolved"

        listed = client.get("/api/v1/oncall/incidents")
        assert listed.status_code == 200
        matches = [
            i
            for i in listed.json()
            if i["fingerprint"] == "fp-track5-dedupe"
        ]
        assert len(matches) == 1
        assert matches[0]["status"] == "resolved"


# ---------------------------------------------------------------------------
# 3. Payload redaction + zero persistent email storage + never logs email
# ---------------------------------------------------------------------------
class TestPayloadRedactionAndEmailPrivacy:
    PROBE_EMAIL = "leak.victim.track5@example.com"
    PROBE_JWT = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "dGVzdHNpZ25hdHVyZXhhbXBsZQ"
    )
    PROBE_BEARER = "Bearer super-secret-token-abc123"

    def test_detail_redacts_email_jwt_and_bearer(
        self, isolated_client, monkeypatch
    ):
        secret = _set_webhook_secret(monkeypatch)
        client, _ = isolated_client
        payload = _webhook_payload(
            fingerprint="fp-track5-redact",
            description=(
                f"contact {self.PROBE_EMAIL} token {self.PROBE_JWT} "
                f"auth {self.PROBE_BEARER} api_key=TOPSECRET123"
            ),
        )
        resp = _post_webhook(client, payload, secret)
        assert resp.status_code == 202, resp.text[:300]
        incident_id = resp.json()["incidents"][0]["id"]

        detail = client.get(f"/api/v1/oncall/incidents/{incident_id}")
        assert detail.status_code == 200
        # Raw secrets must be absent from the whole detail document.
        assert self.PROBE_EMAIL not in detail.text
        assert self.PROBE_JWT not in detail.text
        assert "super-secret-token-abc123" not in detail.text
        assert "TOPSECRET123" not in detail.text
        # Redaction markers prove the scrubber ran.
        assert "[redacted" in detail.text.lower()

        body = detail.json()
        dumped = json.dumps(body)
        assert "@example.com" not in dumped
        assert body["diagnosis"]["read_only_verified"] is True

    def test_webhook_never_logs_email(self, isolated_client, monkeypatch, caplog):
        secret = _set_webhook_secret(monkeypatch)
        client, _ = isolated_client
        with caplog.at_level(logging.DEBUG):
            resp = _post_webhook(
                client,
                _webhook_payload(
                    fingerprint="fp-track5-nolog",
                    description=f"contact {self.PROBE_EMAIL} for triage",
                ),
                secret,
            )
        assert resp.status_code == 202, resp.text[:300]
        assert self.PROBE_EMAIL not in caplog.text

    def test_no_email_column_on_oncall_incident_model(self):
        models = pytest.importorskip(
            "app.models.models",
            reason="Blocked on Track 1 dep: app.models.models unavailable",
        )
        column_names = [c.name for c in models.OnCallIncident.__table__.columns]
        assert not any("email" in name.lower() for name in column_names), (
            f"email column leaked onto oncall_incidents: {column_names}"
        )
        assert not hasattr(models.OnCallIncident, "notification_email")
        assert not hasattr(models.OnCallIncident, "notify_email_once")

    def test_no_email_column_in_models_source(self, repo_root: Path):
        source = (
            repo_root / "backend" / "app" / "models" / "models.py"
        ).read_text(encoding="utf-8")
        oncall_section = source.split("class OnCallIncident", 1)[1]
        # Bound the section to the class body (next top-level class/def).
        assert "email" not in oncall_section.split("\nclass ")[0].lower() or (
            "never emails" in oncall_section.lower()
        ), "OnCallIncident section must not declare an email column"


# ---------------------------------------------------------------------------
# 4-6. History list filters, detail diagnosis, acknowledge
# ---------------------------------------------------------------------------
class TestHistoryListDetailAcknowledge:
    def _seed_two_incidents(self, client, secret: str) -> tuple[str, str]:
        first = _post_webhook(
            client,
            _webhook_payload(
                fingerprint="fp-track5-list-a",
                starts_at="2026-10-26T10:00:00.000Z",
                alertname="HighHttp5xxErrorRate",
                severity="critical",
                service="api",
            ),
            secret,
        ).json()["incidents"][0]
        second = _post_webhook(
            client,
            _webhook_payload(
                fingerprint="fp-track5-list-b",
                starts_at="2026-10-26T11:00:00.000Z",
                alertname="AnalysisWorkerJobFailures",
                severity="warning",
                service="worker",
            ),
            secret,
        ).json()["incidents"][0]
        return first["id"], second["id"]

    def test_list_supports_status_filter_and_limit(
        self, isolated_client, monkeypatch
    ):
        secret = _set_webhook_secret(monkeypatch)
        client, _ = isolated_client
        firing_id, _ = self._seed_two_incidents(client, secret)
        # Acknowledge one so both statuses exist.
        ack = client.post(
            f"/api/v1/oncall/incidents/{firing_id}/acknowledge",
            json={"note": "filter probe"},
        )
        assert ack.status_code == 200

        firing = client.get("/api/v1/oncall/incidents?status=firing")
        assert firing.status_code == 200
        assert all(i["status"] == "firing" for i in firing.json())

        acknowledged = client.get(
            "/api/v1/oncall/incidents?status=acknowledged"
        )
        assert acknowledged.status_code == 200
        assert len(acknowledged.json()) >= 1
        assert all(i["status"] == "acknowledged" for i in acknowledged.json())

        limited = client.get("/api/v1/oncall/incidents?limit=1")
        assert limited.status_code == 200
        assert len(limited.json()) == 1

    def test_detail_contains_read_only_diagnosis_with_plan(
        self, isolated_client, monkeypatch
    ):
        secret = _set_webhook_secret(monkeypatch)
        client, _ = isolated_client
        incident_id, _ = self._seed_two_incidents(client, secret)
        detail = client.get(f"/api/v1/oncall/incidents/{incident_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["id"] == incident_id
        diagnosis = body["diagnosis"]
        assert diagnosis["read_only_verified"] is True
        assert isinstance(diagnosis["recommended_actions"], list)
        assert len(diagnosis["recommended_actions"]) >= 1
        assert isinstance(diagnosis["incident_summary"], str)
        assert diagnosis["incident_summary"]
        assert isinstance(diagnosis["evidence_citations"], list)
        assert 0.0 <= diagnosis["confidence"] <= 1.0

    def test_detail_404_for_unknown_id(self, isolated_client):
        client, _ = isolated_client
        resp = client.get(
            "/api/v1/oncall/incidents/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404

    def test_acknowledge_sets_status_and_note(
        self, isolated_client, monkeypatch
    ):
        secret = _set_webhook_secret(monkeypatch)
        client, _ = isolated_client
        incident_id, _ = self._seed_two_incidents(client, secret)
        resp = client.post(
            f"/api/v1/oncall/incidents/{incident_id}/acknowledge",
            json={"note": "Investigating 5xx spike"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "acknowledged"
        assert body["acknowledge_note"] == "Investigating 5xx spike"
        # Persisted: re-read shows acknowledged + full diagnosis intact.
        detail = client.get(f"/api/v1/oncall/incidents/{incident_id}").json()
        assert detail["status"] == "acknowledged"
        assert detail["acknowledge_note"] == "Investigating 5xx spike"
        assert detail["diagnosis"]["read_only_verified"] is True

    def test_acknowledge_404_for_unknown_id(self, isolated_client):
        client, _ = isolated_client
        resp = client.post(
            "/api/v1/oncall/incidents/00000000-0000-0000-0000-000000000000/acknowledge",
            json={"note": "nope"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. POST /diagnose regression (unchanged JWT endpoint)
# ---------------------------------------------------------------------------
class TestDiagnoseRegression:
    def test_diagnose_still_200(self, isolated_client):
        client, _ = isolated_client
        resp = client.post(
            "/api/v1/oncall/diagnose",
            json={
                "alert_name": "HighAnalysisJobFailureRate",
                "time_window_minutes": 30,
                "context_notes": "history-tab regression probe",
            },
        )
        assert resp.status_code == 200, resp.text[:300]
        assert resp.json()["read_only_verified"] is True


# ---------------------------------------------------------------------------
# 8. Guard rails: read-only agent, score-state + dev-decoupling untouched
# ---------------------------------------------------------------------------
class TestOnCallGuardRails:
    def test_agent_source_has_no_shell_subprocess_or_db_writes(
        self, repo_root: Path
    ):
        source = (
            repo_root / "backend" / "app" / "agents" / "oncall_agent.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "subprocess",
            "os.system",
            "shell=True",
            "shell = True",
            ".commit(",
            ".execute(",
            "session.add",
            "db.add",
            "db.query",
            "DROP TABLE",
            "DELETE FROM",
        ):
            assert forbidden not in source, (
                f"on-call agent must stay read-only; found {forbidden!r}"
            )

    def test_endpoint_never_executes_remediation(self, repo_root: Path):
        source = (
            repo_root
            / "backend"
            / "app"
            / "api"
            / "v1"
            / "endpoints"
            / "oncall.py"
        ).read_text(encoding="utf-8")
        for forbidden in ("subprocess", "os.system", "shell=True"):
            assert forbidden not in source, (
                f"on-call endpoint must never execute fixes; found {forbidden!r}"
            )

    def test_oncall_flow_leaves_score_state_untouched(
        self, isolated_client, monkeypatch
    ):
        """Webhook + acknowledge + diagnose must not alter criterion scores."""
        from app.models import models
        from app.schemas import enums

        secret = _set_webhook_secret(monkeypatch)
        client, Session = isolated_client

        project = client.post(
            "/api/v1/projects",
            json={
                "name": "OnCall Score Guard",
                "github_repo_url": "https://github.com/octocat/hello-world",
            },
        ).json()
        pid = project["id"]
        milestones = client.get(f"/api/v1/projects/{pid}/milestones").json()[
            "assessment_milestones"
        ]
        run_id = client.get(f"/api/v1/projects/{pid}/analyses").json()[0]["id"]

        db = Session()
        try:
            for am in milestones[:2]:
                db.add(
                    models.CriterionAssessment(
                        analysis_run_id=UUID(run_id),
                        project_id=UUID(pid),
                        assessment_milestone_id=UUID(am["id"]),
                        criterion_code=am.get("criterion_code", "ci_cd"),
                        max_points=am.get("max_points", 2),
                        ai_proposed_points=1,
                        ai_reasoning="guard reasoning (on-call must not touch)",
                        ai_confidence=0.7,
                        missing_for_next_level="guard next level",
                        score_state=enums.ScoreState.ESTIMATED,
                        evidence_ids=[],
                    )
                )
            db.commit()
            before = [
                (
                    r.ai_proposed_points,
                    r.ai_reasoning,
                    str(r.score_state),
                    r.human_override_points,
                )
                for r in db.query(models.CriterionAssessment)
                .filter(models.CriterionAssessment.project_id == UUID(pid))
                .order_by(models.CriterionAssessment.criterion_code)
                .all()
            ]
        finally:
            db.close()

        # Full on-call flow: diagnose + webhook + acknowledge.
        assert (
            client.post(
                "/api/v1/oncall/diagnose",
                json={
                    "alert_name": "HighHttp5xxErrorRate",
                    "time_window_minutes": 30,
                },
            ).status_code
            == 200
        )
        incident_id = (
            _post_webhook(
                client, _webhook_payload(fingerprint="fp-track5-guard"), secret
            )
            .json()["incidents"][0]["id"]
        )
        assert (
            client.post(
                f"/api/v1/oncall/incidents/{incident_id}/acknowledge",
                json={"note": "guard probe"},
            ).status_code
            == 200
        )

        db = Session()
        try:
            after = [
                (
                    r.ai_proposed_points,
                    r.ai_reasoning,
                    str(r.score_state),
                    r.human_override_points,
                )
                for r in db.query(models.CriterionAssessment)
                .filter(models.CriterionAssessment.project_id == UUID(pid))
                .order_by(models.CriterionAssessment.criterion_code)
                .all()
            ]
        finally:
            db.close()
        assert after == before
        assert all(
            points == 1
            and state == enums.ScoreState.ESTIMATED
            for points, _, state, _ in after
        )

    def test_dev_completion_still_decoupled_after_oncall(
        self, isolated_client, monkeypatch
    ):
        """Completing dev tasks moves dev_completion_pct, never assessment."""
        from app.models import models
        from app.schemas import enums

        _set_webhook_secret(monkeypatch)
        client, Session = isolated_client

        project = client.post(
            "/api/v1/projects",
            json={
                "name": "OnCall Decoupling Guard",
                "github_repo_url": "https://github.com/octocat/hello-world",
            },
        ).json()
        pid = project["id"]
        milestones = client.get(f"/api/v1/projects/{pid}/milestones").json()[
            "assessment_milestones"
        ]
        parent_id = milestones[0]["id"]
        dev_id = client.post(
            f"/api/v1/projects/{pid}/development-milestones",
            json={"assessment_milestone_id": parent_id, "title": "guard task"},
        ).json()["id"]
        run_id = client.get(f"/api/v1/projects/{pid}/analyses").json()[0]["id"]

        db = Session()
        try:
            db.add(
                models.CriterionAssessment(
                    analysis_run_id=UUID(run_id),
                    project_id=UUID(pid),
                    assessment_milestone_id=UUID(parent_id),
                    criterion_code=milestones[0].get("criterion_code", "ci_cd"),
                    max_points=milestones[0].get("max_points", 2),
                    ai_proposed_points=1,
                    ai_reasoning="decoupling guard reasoning",
                    ai_confidence=0.7,
                    score_state=enums.ScoreState.ESTIMATED,
                    evidence_ids=[],
                )
            )
            db.commit()
        finally:
            db.close()

        resp = client.patch(
            f"/api/v1/projects/{pid}/development-milestones/{dev_id}",
            json={"status": "completed"},
        )
        assert resp.status_code == 200

        db = Session()
        try:
            row = (
                db.query(models.CriterionAssessment)
                .filter(models.CriterionAssessment.project_id == UUID(pid))
                .one()
            )
            assert row.ai_proposed_points == 1
            assert row.ai_reasoning == "decoupling guard reasoning"
            assert row.human_override_points is None
        finally:
            db.close()


# ---------------------------------------------------------------------------
# A+B: scanner -> incident bridge + ?project_id scoping (Track 1 creator,
# Track 3 bridge call, Track 4 banner + scoped UI).
# ---------------------------------------------------------------------------
class TestSecurityScannerBridge:
    """Bridge creates firing SecurityCritical:{rule_id} rows (Track 1 creator)."""

    def _make_project(self, client, name="Bridge Probe"):
        proj = client.post(
            "/api/v1/projects",
            json={
                "name": name,
                "github_repo_url": "https://github.com/octocat/hello-world",
            },
        ).json()
        return proj["id"]

    def test_bridge_creates_firing_security_critical_row(
        self, isolated_client, monkeypatch
    ):
        import hashlib
        import json
        import re

        from app.api.v1.endpoints.oncall import create_security_incident
        from app.models import models

        _set_webhook_secret(monkeypatch)
        client, Session = isolated_client
        pid = self._make_project(client)

        db = Session()
        try:
            row = create_security_incident(
                db,
                project_id=UUID(pid),
                rule_id="semgrep.python.lang.security.use-def",
                severity="critical",
                file_path="app/main.py",
                commit_sha="abc123def456",
                summary="Critical finding; contact owner@example.com for triage",
                remediation_hints=["Rotate api_key=TOPSECRET123 and redeploy"],
            )
            assert row.alert_name == "SecurityCritical:semgrep.python.lang.security.use-def"
            assert row.severity == "critical"
            assert row.service == "security-scanner"
            assert str(row.status) == "firing"
            assert row.read_only_verified is True
            assert str(row.project_id) == pid
            assert re.fullmatch(r"[0-9a-f]{32}", row.fingerprint), row.fingerprint
            expected = hashlib.sha256(
                "semgrep.python.lang.security.use-def|app/main.py|abc123def456".encode()
            ).hexdigest()[:32]
            assert row.fingerprint == expected
            assert row.confidence == 0.75
            # Diagnosis shaped like OnCallDiagnosisResponse.
            assert row.diagnosis_json["read_only_verified"] is True
            assert row.diagnosis_json["confidence"] == 0.75
            assert row.diagnosis_json["evidence_citations"][0]["source"] == "security-scanner"
            assert row.diagnosis_json["evidence_citations"][0]["query"] == (
                "semgrep.python.lang.security.use-def"
            )
            assert isinstance(row.diagnosis_json["recommended_actions"], list)
            dumped = json.dumps(
                {"payload": row.alert_payload_json, "diag": row.diagnosis_json}
            )
            assert "owner@example.com" not in dumped
            assert "TOPSECRET123" not in dumped
            assert "@example.com" not in dumped
            assert "[redacted" in dumped.lower()
            # No email column anywhere on the bridge row.
            assert not any(
                "email" in c.name.lower()
                for c in models.OnCallIncident.__table__.columns
            )
        finally:
            db.close()

    def test_bridge_severity_high_passthrough(self, isolated_client, monkeypatch):
        from app.api.v1.endpoints.oncall import create_security_incident

        _set_webhook_secret(monkeypatch)
        client, Session = isolated_client
        pid = self._make_project(client, name="Bridge High Probe")
        db = Session()
        try:
            row = create_security_incident(
                db,
                project_id=UUID(pid),
                rule_id="bandit.B105",
                severity="high",
                file_path="app/worker.py",
                commit_sha="sha-high-001",
                summary="Hardcoded password string",
                remediation_hints=["Move secret to env var"],
            )
            assert row.severity == "high"
            assert row.service == "security-scanner"
            assert row.alert_name == "SecurityCritical:bandit.B105"
        finally:
            db.close()

    def test_bridge_redacts_jwt_and_bearer(self, isolated_client, monkeypatch):
        import json

        from app.api.v1.endpoints.oncall import create_security_incident

        _set_webhook_secret(monkeypatch)
        client, Session = isolated_client
        pid = self._make_project(client, name="Bridge Redact Probe")
        probe_jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            "dGVzdHNpZ25hdHVyZXhhbXBsZQ"
        )
        db = Session()
        try:
            row = create_security_incident(
                db,
                project_id=UUID(pid),
                rule_id="gitleaks.generic-api-key",
                severity="critical",
                file_path="app/config.py",
                commit_sha="sha-redact-001",
                summary=(
                    f"leaked {probe_jwt} auth Bearer super-secret-token-abc123 "
                    "contact leak.victim.track5@example.com"
                ),
                remediation_hints=["revoke Bearer super-secret-token-abc123 now"],
            )
            dumped = json.dumps(
                {"payload": row.alert_payload_json, "diag": row.diagnosis_json}
            )
            assert probe_jwt not in dumped
            assert "super-secret-token-abc123" not in dumped
            assert "leak.victim.track5@example.com" not in dumped
            assert "[redacted" in dumped.lower()
        finally:
            db.close()

    def test_bridge_dedupe_same_rule_path_sha_returns_one_row(
        self, isolated_client, monkeypatch
    ):
        from app.api.v1.endpoints.oncall import create_security_incident
        from app.models import models

        _set_webhook_secret(monkeypatch)
        client, Session = isolated_client
        pid = self._make_project(client, name="Bridge Dedupe Probe")
        db = Session()
        try:
            first = create_security_incident(
                db,
                project_id=UUID(pid),
                rule_id="semgrep.dedupe.rule",
                severity="critical",
                file_path="app/dup.py",
                commit_sha="sha-dedupe-001",
                summary="first",
                remediation_hints=["fix it"],
            )
            first_id = str(first.id)
            second = create_security_incident(
                db,
                project_id=UUID(pid),
                rule_id="semgrep.dedupe.rule",
                severity="critical",
                file_path="app/dup.py",
                commit_sha="sha-dedupe-001",
                summary="second (same rule+path+sha)",
                remediation_hints=["fix it"],
            )
            assert str(second.id) == first_id
            count = (
                db.query(models.OnCallIncident)
                .filter(
                    models.OnCallIncident.fingerprint == first.fingerprint,
                    models.OnCallIncident.project_id == UUID(pid),
                )
                .count()
            )
            assert count == 1
        finally:
            db.close()

    def test_bridge_different_commit_sha_creates_new_row(
        self, isolated_client, monkeypatch
    ):
        from app.api.v1.endpoints.oncall import create_security_incident
        from app.models import models

        _set_webhook_secret(monkeypatch)
        client, Session = isolated_client
        pid = self._make_project(client, name="Bridge New SHA Probe")
        db = Session()
        try:
            first = create_security_incident(
                db,
                project_id=UUID(pid),
                rule_id="semgrep.newsha.rule",
                severity="critical",
                file_path="app/a.py",
                commit_sha="sha-aaa-001",
                summary="sha a",
            )
            second = create_security_incident(
                db,
                project_id=UUID(pid),
                rule_id="semgrep.newsha.rule",
                severity="critical",
                file_path="app/a.py",
                commit_sha="sha-bbb-002",
                summary="sha b",
            )
            assert str(second.id) != str(first.id)
            assert second.fingerprint != first.fingerprint
            count = (
                db.query(models.OnCallIncident)
                .filter(models.OnCallIncident.project_id == UUID(pid))
                .count()
            )
            assert count == 2
        finally:
            db.close()

    def test_webhook_rows_still_project_id_none(
        self, isolated_client, monkeypatch
    ):
        secret = _set_webhook_secret(monkeypatch)
        client, _ = isolated_client
        resp = _post_webhook(
            client, _webhook_payload(fingerprint="fp-track5-bridge-null"), secret
        )
        assert resp.status_code == 202
        assert resp.json()["incidents"][0]["project_id"] is None

    def test_project_id_filter_scoped_global_and_invalid(
        self, isolated_client, monkeypatch
    ):
        from app.api.v1.endpoints.oncall import create_security_incident

        secret = _set_webhook_secret(monkeypatch)
        client, Session = isolated_client
        pid_a = self._make_project(client, name="Bridge Scope A")
        pid_b = self._make_project(client, name="Bridge Scope B")

        db = Session()
        try:
            create_security_incident(
                db,
                project_id=UUID(pid_a),
                rule_id="semgrep.scope.a",
                severity="critical",
                file_path="app/a.py",
                commit_sha="sha-scope-a",
                summary="scope a",
            )
            create_security_incident(
                db,
                project_id=UUID(pid_b),
                rule_id="semgrep.scope.b",
                severity="high",
                file_path="app/b.py",
                commit_sha="sha-scope-b",
                summary="scope b",
            )
        finally:
            db.close()
        # Global webhook row (project_id=None) exists alongside scoped rows.
        _post_webhook(
            client, _webhook_payload(fingerprint="fp-track5-scope-global"), secret
        )

        scoped_a = client.get(f"/api/v1/oncall/incidents?project_id={pid_a}")
        assert scoped_a.status_code == 200, scoped_a.text[:300]
        rows_a = scoped_a.json()
        assert len(rows_a) == 1
        assert rows_a[0]["project_id"] == pid_a
        assert rows_a[0]["alert_name"] == "SecurityCritical:semgrep.scope.a"

        scoped_b = client.get(f"/api/v1/oncall/incidents?project_id={pid_b}")
        assert scoped_b.status_code == 200
        assert len(scoped_b.json()) == 1
        assert scoped_b.json()[0]["project_id"] == pid_b

        unscoped = client.get("/api/v1/oncall/incidents")
        assert unscoped.status_code == 200
        # Omitted ?project_id returns the global view (scoped + unscoped rows).
        assert len(unscoped.json()) >= 3

        bad = client.get("/api/v1/oncall/incidents?project_id=not-a-uuid")
        assert bad.status_code == 422, bad.text[:300]

    def test_bridge_never_touches_criterion_assessments(
        self, isolated_client, monkeypatch
    ):
        from app.api.v1.endpoints.oncall import create_security_incident
        from app.models import models
        from app.schemas import enums

        _set_webhook_secret(monkeypatch)
        client, Session = isolated_client
        pid = self._make_project(client, name="Bridge Guard Probe")
        milestones = client.get(f"/api/v1/projects/{pid}/milestones").json()[
            "assessment_milestones"
        ]
        run_id = client.get(f"/api/v1/projects/{pid}/analyses").json()[0]["id"]

        db = Session()
        try:
            for am in milestones[:2]:
                db.add(
                    models.CriterionAssessment(
                        analysis_run_id=UUID(run_id),
                        project_id=UUID(pid),
                        assessment_milestone_id=UUID(am["id"]),
                        criterion_code=am.get("criterion_code", "ci_cd"),
                        max_points=am.get("max_points", 2),
                        ai_proposed_points=1,
                        ai_reasoning="bridge guard reasoning",
                        ai_confidence=0.7,
                        missing_for_next_level="guard next level",
                        score_state=enums.ScoreState.ESTIMATED,
                        evidence_ids=[],
                    )
                )
            db.commit()
            before = [
                (
                    r.ai_proposed_points,
                    r.ai_reasoning,
                    str(r.score_state),
                    r.human_override_points,
                )
                for r in db.query(models.CriterionAssessment)
                .filter(models.CriterionAssessment.project_id == UUID(pid))
                .order_by(models.CriterionAssessment.criterion_code)
                .all()
            ]
        finally:
            db.close()

        db = Session()
        try:
            create_security_incident(
                db,
                project_id=UUID(pid),
                rule_id="semgrep.guard.rule",
                severity="critical",
                file_path="app/guard.py",
                commit_sha="sha-guard-001",
                summary="guard finding",
                remediation_hints=["review manually"],
            )
        finally:
            db.close()

        db = Session()
        try:
            after = [
                (
                    r.ai_proposed_points,
                    r.ai_reasoning,
                    str(r.score_state),
                    r.human_override_points,
                )
                for r in db.query(models.CriterionAssessment)
                .filter(models.CriterionAssessment.project_id == UUID(pid))
                .order_by(models.CriterionAssessment.criterion_code)
                .all()
            ]
        finally:
            db.close()
        assert after == before
        assert all(
            points == 1 and state == enums.ScoreState.ESTIMATED
            for points, _, state, _ in after
        )

    def test_bridge_uses_stable_creator_no_direct_model_writes(
        self, repo_root: Path
    ):
        pipeline = (
            repo_root / "backend" / "app" / "services" / "analysis_pipeline.py"
        ).read_text(encoding="utf-8")
        assert "create_security_incident" in pipeline
        assert "OnCallIncident(" not in pipeline
        worker_dir = repo_root / "backend" / "app" / "worker"
        if worker_dir.is_dir():
            for path in worker_dir.rglob("*.py"):
                assert "OnCallIncident(" not in path.read_text(encoding="utf-8"), (
                    f"worker must call the Track-1 creator, not the model: {path}"
                )
        services_dir = repo_root / "backend" / "app" / "services"
        for path in services_dir.glob("*.py"):
            if path.name == "analysis_pipeline.py":
                continue
            assert "OnCallIncident(" not in path.read_text(encoding="utf-8"), (
                f"only _persist_security_report may bridge: {path.name}"
            )

    def test_bridge_failure_does_not_fail_run(self, isolated_client, monkeypatch):
        """Creator exception is swallowed; the security report still persists."""
        from app.models import models
        from app.services import analysis_pipeline as pipeline_mod
        from app.services.security_scanner import NormalizedFinding, ScanSummary

        _set_webhook_secret(monkeypatch)
        client, Session = isolated_client
        pid = self._make_project(client, name="Bridge Failure Probe")
        run_id = client.get(f"/api/v1/projects/{pid}/analyses").json()[0]["id"]

        def _boom(*args, **kwargs):
            raise RuntimeError("bridge creator exploded (test probe)")

        monkeypatch.setattr(
            "app.api.v1.endpoints.oncall.create_security_incident", _boom
        )
        result = pipeline_mod.PipelineResult(
            commit_sha="sha-bridge-fail-001",
            previous_commit_sha=None,
            dev_completion_pct=0.0,
            summary_markdown="probe",
            security=ScanSummary(
                scanners_executed=["semgrep"],
                scanners_skipped=[],
                findings=[
                    NormalizedFinding(
                        scanner="semgrep",
                        rule_id="semgrep.fail.rule",
                        severity="critical",
                        file_path="app/fail.py",
                        message="boom",
                    )
                ],
                overall_status="critical",
            ),
        )
        db = Session()
        try:
            # Must not raise even though the bridge creator raises.
            pipeline_mod._persist_security_report(
                db,
                analysis_run_id=UUID(run_id),
                project_id=UUID(pid),
                result=result,
            )
            db.commit()
            report = (
                db.query(models.SecurityReport)
                .filter(models.SecurityReport.analysis_run_id == UUID(run_id))
                .one_or_none()
            )
            assert report is not None, "security report must persist despite bridge failure"
        finally:
            db.close()
