"""Service-layer Protocol interfaces so Track 1 endpoints compile and boot
without Track 2 (AI agents) / Track 3 (worker, scanners, monitors).

Contract:
- Endpoints depend ONLY on the `get_*` getters below via
  `fastapi.Depends` (the Protocol type is the prod path). Track 2/3 wire
  real implementations through `app.dependency_overrides[get_*]`.
- The `Stub*` classes are TEST-ONLY doubles (plus a degraded-safe
  fallback when no override is registered). No endpoint imports a `Stub*`
  directly — they resolve through the getter so overrides are honored.
- Endpoints perform no raw httpx/LLM calls; SSRF + secrets handling live
  in Track 2/3 implementations.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DeploymentMonitorProtocol(Protocol):
    """Track 3: SSRF-protected httpx health check (see backend/AGENTS.md §2.3)."""

    def check(self, target_url: str) -> dict:
        """Return {is_reachable, http_status_code, https_valid,
        response_time_ms, error_detail}."""
        ...


class StubDeploymentMonitor:
    """TEST-ONLY double: records that no live check ran yet."""

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
    """Resolve the deployment monitor (override point for Track 3).

    Prefers the real Track 3 `DeploymentMonitor` when importable;
    otherwise returns the test-only stub so the contract route still
    responds with a degraded-safe row instead of 500.
    """
    try:
        from app.services.deployment_monitor import DeploymentMonitor

        return DeploymentMonitor()
    except Exception:
        return StubDeploymentMonitor()


@runtime_checkable
class RubricAnalystProtocol(Protocol):
    """Track 2: rubric extraction/evaluation via Gemini structured outputs."""

    def extract_rubric(
        self, raw_content: str | None, source_url: str | None
    ) -> dict[str, Any]:
        ...


class StubRubricAnalyst:
    """TEST-ONLY double: extraction not wired yet (Track 2 TODO)."""

    def extract_rubric(
        self, raw_content: str | None, source_url: str | None
    ) -> dict[str, Any]:
        return {
            "criteria": [],
            "note": "rubric_analyst not wired yet (Track 2 TODO)",
        }


def get_rubric_analyst() -> RubricAnalystProtocol:
    """Resolve the rubric analyst (override point for Track 2)."""
    try:
        from app.agents.rubric_analyst import RubricAnalyst  # type: ignore

        return RubricAnalyst()
    except Exception:
        try:
            from app.services.rubric_service import RubricAnalyst  # type: ignore

            return RubricAnalyst()
        except Exception:
            return StubRubricAnalyst()


@runtime_checkable
class OnCallAgentProtocol(Protocol):
    """Track 2 (Phase 4): bounded read-only on-call diagnosis."""

    def diagnose(
        self, alert_name: str, time_window_minutes: int, context_notes: str | None
    ) -> dict:
        ...


class StubOnCallAgent:
    """TEST-ONLY double: deterministic read-only placeholder diagnosis."""

    def diagnose(
        self, alert_name: str, time_window_minutes: int, context_notes: str | None
    ) -> dict:
        return {
            "incident_summary": (
                f"Received alert '{alert_name}' "
                f"(window: last {time_window_minutes} minutes). "
                "Automated read-only triage is not wired yet (Track 2 TODO)."
            ),
            "root_cause_hypothesis": (
                "No telemetry inspected yet — on-call agent stub. Context notes: "
                f"{context_notes or 'none provided'}."
            ),
            "confidence": 0.0,
            "evidence_citations": [],
            "recommended_actions": [
                "Wire the bounded read-only on-call agent (Track 2) for this alert.",
                "Check worker analysis job status and DB pool metrics manually.",
                "Consider raising ANALYSIS_TIMEOUT_SECONDS or enforcing shallow clones.",
            ],
            "read_only_verified": True,
        }


def get_oncall_agent() -> OnCallAgentProtocol:
    """Resolve the on-call agent (override point for Track 2, Phase 4)."""
    try:
        from app.agents.oncall_agent import OnCallAgent  # type: ignore

        return OnCallAgent()
    except Exception:
        return StubOnCallAgent()
