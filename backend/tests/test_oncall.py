"""Phase 4 tests: Bounded Read-Only On-Call Agent, Alert Rules & Telemetry Correlation.

Covers Issues #6 ([obs] Trace-ID metrics+logs+traces), #7 ([alerts] User-impact
alerts firing), and #8 ([oncall] Agent wakes on alert).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.unit]


class TestOnCallAgentDiagnosis:
    def test_diagnose_endpoint_returns_structured_read_only_diagnosis(
        self, isolated_client
    ):
        """Issue #8: POST /api/v1/oncall/diagnose returns structured diagnosis + read_only_verified."""
        client, _ = isolated_client
        resp = client.post(
            "/api/v1/oncall/diagnose",
            json={
                "alert_name": "HighAnalysisJobFailureRate",
                "time_window_minutes": 30,
                "context_notes": "Worker jobs timing out on large repositories",
            },
        )
        assert resp.status_code == 200, resp.text[:300]
        body = resp.json()
        assert body["read_only_verified"] is True
        assert "HighAnalysisJobFailureRate" in body["incident_summary"]
        assert isinstance(body["root_cause_hypothesis"], str) and body["root_cause_hypothesis"]
        assert isinstance(body["evidence_citations"], list) and len(body["evidence_citations"]) >= 1
        assert isinstance(body["recommended_actions"], list) and len(body["recommended_actions"]) >= 1
        assert 0.0 <= body["confidence"] <= 1.0

    def test_oncall_agent_class_resolves_via_protocol(self):
        """Track 1 protocol getter resolves Track 2 OnCallAgent (not StubOnCallAgent)."""
        pytest.importorskip("pydantic")
        from app.agents.oncall_agent import OnCallAgent
        from app.api.protocols import get_oncall_agent

        agent = get_oncall_agent()
        assert isinstance(agent, OnCallAgent)
        diagnosis = agent.diagnose(
            "HighAnalysisJobFailureRate",
            30,
            "Worker jobs timing out on large repositories",
        )
        assert diagnosis["read_only_verified"] is True
        assert diagnosis["evidence_citations"][0]["source"] in {
            "prometheus",
            "loki",
            "tempo",
            "postgres_jobs",
        }


class TestObservabilityCorrelationAndAlerts:
    def test_trigger_analysis_correlates_trace_id_without_leaking_email(
        self, isolated_client, caplog
    ):
        """Issue #6: POST /api/v1/projects/{id}/analyses emits metrics + logs + trace_id header, zero email leak."""
        client, _ = isolated_client
        proj = client.post(
            "/api/v1/projects",
            json={
                "name": "Telemetry Correlation Probe",
                "github_repo_url": "https://github.com/octocat/hello-world",
            },
        ).json()
        secret_email = "secret-telemetry-probe@example.com"
        with caplog.at_level(logging.INFO):
            resp = client.post(
                f"/api/v1/projects/{proj['id']}/analyses",
                json={
                    "notify_email_once": secret_email,
                    "acknowledge_ephemeral_email": True,
                },
            )
        assert resp.status_code == 202
        trace_id = resp.headers.get("X-Trace-Id")
        assert trace_id and len(trace_id) == 32
        # Structured logs carry the exact same trace_id
        assert f"trace_id={trace_id}" in caplog.text
        # Never leak email into logs or metrics
        assert secret_email not in caplog.text
        metrics_resp = client.get("/metrics")
        assert metrics_resp.status_code == 200
        assert "http_requests_total" in metrics_resp.text
        assert secret_email not in metrics_resp.text

    def test_prometheus_alert_rules_cover_all_four_user_impact_slis(
        self, repo_root: Path
    ):
        """Issue #7: infra/prometheus/alert_rules.yml defines the 4 user-impact alerts."""
        rules_file = repo_root / "infra" / "prometheus" / "alert_rules.yml"
        assert rules_file.is_file()
        content = rules_file.read_text(encoding="utf-8")
        for alert_name in (
            "HighHttp5xxErrorRate",
            "HighApiLatencyP95",
            "AnalysisWorkerJobFailures",
            "TargetDeploymentDown",
        ):
            assert f"alert: {alert_name}" in content

