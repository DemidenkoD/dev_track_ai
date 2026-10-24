"""Service-layer Protocol interfaces so Track 1 endpoints compile and boot
without Track 2 (AI agents) / Track 3 (worker, scanners, monitors).

Track 2/3 will provide concrete implementations and wire them here via
FastAPI dependency overrides. Until then, endpoints use deterministic
DB-backed behaviour or explicit stubs — never raw httpx/LLM calls.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class DeploymentMonitorProtocol(Protocol):
    """Track 3: SSRF-protected httpx health check (see backend/AGENTS.md §2.3).

    TODO(Track 3): implement in backend/app/services/deployment_monitor.py
    with socket.getaddrinfo IP validation + redirect re-validation, then
    override `get_deployment_monitor` in deployments endpoints.
    """

    def check(self, target_url: str) -> dict:
        """Return {is_reachable, http_status_code, https_valid,
        response_time_ms, error_detail}."""
        ...


class StubDeploymentMonitor:
    """Deterministic placeholder: records that no live check ran yet."""

    def check(self, target_url: str) -> dict:
        return {
            "is_reachable": False,
            "http_status_code": None,
            "https_valid": target_url.startswith("https://"),
            "response_time_ms": None,
            "error_detail": (
                "deployment_monitor not wired yet (Track 3 TODO): "
                "no live HTTP request performed"
            ),
        }


def get_deployment_monitor() -> DeploymentMonitorProtocol:
    return StubDeploymentMonitor()


@runtime_checkable
class RubricAnalystProtocol(Protocol):
    """Track 2: rubric extraction/evaluation via Gemini structured outputs.

    TODO(Track 2): implement in backend/app/agents/rubric_analyst.py and
    backend/app/services/rubric_service.py, then override
    `get_rubric_analyst` in the rubrics ingest endpoint.
    """

    def extract_rubric(self, raw_content: str | None, source_url: str | None) -> dict:
        ...


@runtime_checkable
class OnCallAgentProtocol(Protocol):
    """Track 2 (Phase 4): bounded read-only on-call diagnosis.

    TODO(Track 2): implement in backend/app/agents/oncall_agent.py, then
    override `get_oncall_agent` in the oncall endpoint.
    """

    def diagnose(
        self, alert_name: str, time_window_minutes: int, context_notes: str | None
    ) -> dict:
        ...


def latest_analysis_run_id_placeholder(project_id: UUID) -> None:
    """Reserved helper hook for the Track 3 analysis pipeline wiring."""
    return None
