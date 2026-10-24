"""Bounded read-only On-Call Agent (Track 2, Phase 4).

Diagnoses user-impacting alerts (HTTP 5xx spikes, worker timeouts, DB pool
exhaustion) over read-only telemetry: Prometheus metric queries, Loki log
streams, Tempo trace summaries, and the alert payload.

Hard safety boundary: this agent has ZERO shell execution, ZERO database
mutation, and ZERO remediation-execution tools. It only reads telemetry and
proposes safe human-approved steps. Every output sets
``read_only_verified=True``; any code path that cannot uphold read-only
operation must fail closed to the deterministic fallback (which also sets
``read_only_verified=True``).
"""

from __future__ import annotations

from typing import Any, Sequence

from app.agents.base import run_with_fallback

from app.schemas.agent_outputs import OnCallDiagnosisOutput, TelemetryCitation

ONCALL_SYSTEM = (
    "You are DevTrack AI's bounded read-only on-call diagnostician. You may "
    "ONLY inspect the provided Prometheus metrics, Loki logs, Tempo traces, "
    "and alert payload to hypothesize a root cause. You must NEVER propose or "
    "assume shell execution, database writes, config mutation, or automated "
    "remediation — only safe human-approved runbook steps. Cite every claim "
    "with evidence_citations (source/query/excerpt). Always return "
    "read_only_verified=true. If telemetry is insufficient, say so and lower "
    "confidence rather than guessing."
)

_ALLOWED_SOURCES = {"prometheus", "loki", "tempo", "postgres_jobs"}


def _telemetry_to_text(
    metric_queries: Sequence[Any] | None,
    log_streams: Sequence[Any] | None,
    trace_summaries: Sequence[Any] | None,
    limit: int = 20,
) -> str:
    parts: list[str] = []

    def _fmt(items: Sequence[Any] | None, label: str) -> None:
        if not items:
            parts.append(f"{label}: (none provided)")
            return
        lines = []
        for item in list(items)[:limit]:
            if isinstance(item, dict):
                lines.append(
                    f"- query={item.get('query', '?')} :: "
                    f"{str(item.get('result', item.get('excerpt', '')))[:400]}"
                )
            else:
                lines.append(f"- {str(item)[:400]}")
        parts.append(f"{label}:\n" + "\n".join(lines))

    _fmt(metric_queries, "PROMETHEUS METRICS (read-only)")
    _fmt(log_streams, "LOKI LOG STREAMS (read-only)")
    _fmt(trace_summaries, "TEMPO TRACE SUMMARIES (read-only)")
    return "\n\n".join(parts)


def fallback_diagnosis(
    alert_name: str = "unknown",
    time_window_minutes: int = 30,
    context_notes: str | None = None,
    error: Exception | None = None,  # noqa: ARG001
) -> OnCallDiagnosisOutput:
    """Fail-closed deterministic diagnosis (read-only flag always True)."""
    notes = (context_notes or "no additional context").strip()[:500]
    excerpt = (
        f"Alert `{alert_name}` fired within the last {time_window_minutes} min. "
        f"Context: {notes}. Telemetry unavailable to the offline fallback."
    )
    return OnCallDiagnosisOutput(
        incident_summary=(
            f"Offline fallback triage for alert `{alert_name}` "
            f"({time_window_minutes} min window). Gemini/telemetry unavailable; "
            "no automated action taken."
        ),
        root_cause_hypothesis=(
            "Unknown — insufficient telemetry in offline mode. Most common "
            "causes for this class: worker timeout on large repos, DB pool "
            "exhaustion, or upstream deployment 5xx. Requires human review of "
            "Prometheus/Loki/Tempo."
        ),
        confidence=0.25,
        evidence_citations=[
            TelemetryCitation(
                source="loki",
                query='{app="worker"} |= "ERROR"',
                excerpt=excerpt[:500],
            )
        ],
        recommended_actions=[
            "Inspect worker logs for TimeoutError / OOM around the alert window (read-only).",
            "Check Prometheus http_requests_5xx_total and worker job failure rate dashboards.",
            "Verify DB pool saturation and analysis job queue depth before changing anything.",
            "Human approval required before any restart, scaling, or config change — this agent takes no action itself.",
        ],
        read_only_verified=True,
    )


def diagnose_incident(
    alert_name: str,
    time_window_minutes: int = 30,
    context_notes: str | None = None,
    metric_queries: Sequence[Any] | None = None,
    log_streams: Sequence[Any] | None = None,
    trace_summaries: Sequence[Any] | None = None,
) -> OnCallDiagnosisOutput:
    """Read-only incident diagnosis over telemetry (no side effects)."""
    window = max(5, min(int(time_window_minutes or 30), 1440))

    def _prompt() -> tuple[str, str]:
        user = (
            f"ALERT: {alert_name} | window={window} minutes\n"
            f"Context notes: {(context_notes or '(none)')[:1000]}\n\n"
            f"{_telemetry_to_text(metric_queries, log_streams, trace_summaries)}\n\n"
            "Diagnose: incident_summary, root_cause_hypothesis, confidence, "
            "evidence_citations (allowed sources: prometheus, loki, tempo, "
            "postgres_jobs), recommended_actions (human-approved runbook steps "
            "only), read_only_verified=true."
        )
        return (ONCALL_SYSTEM, user)

    def _parse(raw: dict[str, Any]) -> OnCallDiagnosisOutput:
        # Enforce read-only flag and source allowlist regardless of model output.
        # Unknown sources are rejected (never silently coerced) so telemetry
        # citations stay auditable.
        raw = dict(raw)
        raw["read_only_verified"] = True
        citations = []
        for c in raw.get("evidence_citations", []) or []:
            if isinstance(c, dict) and c.get("source") not in _ALLOWED_SOURCES:
                raise ValueError(
                    f"Unknown telemetry source {c.get('source')!r}; allowed: "
                    f"{sorted(_ALLOWED_SOURCES)}"
                )
            citations.append(c)
        raw["evidence_citations"] = citations
        return OnCallDiagnosisOutput.model_validate(raw)

    return run_with_fallback(
        prompt_builder=_prompt,
        response_schema=OnCallDiagnosisOutput,
        parse=_parse,
        fallback=lambda exc: fallback_diagnosis(alert_name, window, context_notes, exc),
    )
