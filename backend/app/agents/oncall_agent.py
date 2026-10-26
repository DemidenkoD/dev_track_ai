"""Bounded read-only On-Call Agent (Track 2, Phase 4).

Diagnoses user-impacting alerts (API error spikes, worker timeouts, DB pool
exhaustion) over read-only telemetry: Prometheus metric queries, Loki log
streams, Tempo trace summaries, and the alert payload.

Hard safety boundary: this agent has ZERO shell use, ZERO database
mutation, and ZERO remediation-running tools. It only reads telemetry and
proposes safe human-approved steps shown as display text only. Every output
sets ``read_only_verified=True``; any code path that cannot uphold read-only
operation must fail closed to the deterministic fallback (which also sets
``read_only_verified=True``).
"""

from __future__ import annotations

import re
from typing import Any, Sequence

from app.agents.base import run_with_fallback

from app.schemas.agent_outputs import OnCallDiagnosisOutput, TelemetryCitation

ONCALL_SYSTEM = (
    "You are DevTrack AI's bounded read-only on-call diagnostician writing "
    "for the History tab, for a non-expert human reader. You may ONLY inspect "
    "the provided Prometheus metrics, Loki logs, Tempo traces, and alert "
    "payload to hypothesize a root cause. You must NEVER propose or assume "
    "shell commands, database writes, config changes, or automatic fixes — "
    "only safe human-approved runbook steps shown as display text. "
    "Style rules (History-tab readability): "
    "(1) incident_summary is 1-2 plain sentences with no metric jargon — say "
    "'API errors spiked', never '5xx share >5%'; always name the alert and "
    "time window in plain words. "
    "(2) root_cause_hypothesis states the single most-likely cause in plain "
    "words, then adds one sentence on what telemetry was checked "
    "(Prometheus/Loki/Tempo) and what is still unknown. "
    "(3) recommended_actions is a remediation plan of 3-5 numbered steps "
    "in plain verbs ('1. Check X', '2. Compare Y', '3. Ask a human to approve Z'), "
    "ordered by value (quick safe checks first, risky restarts last), each step "
    "runnable by a human, never implying this agent takes action itself. "
    "(4) Lower confidence when telemetry is missing or thin; never guess. "
    "(5) Cite every claim with evidence_citations (source/query/excerpt); "
    "keep each excerpt under 500 characters and truncatable. "
    "(6) Never include emails, JWTs, tokens, passwords, or key material in ANY "
    "field — redact to '[redacted]'. "
    "Always return read_only_verified=true."
)

_ALLOWED_SOURCES = {"prometheus", "loki", "tempo", "postgres_jobs"}

_EXCERPT_LIMIT = 450

# Plain-language labels per known alert (History tab: no metric jargon).
_ALERT_PLAIN_LABELS = {
    "highhttp5xxerrorrate": "API errors spiked",
    "highapilatencyp95": "API responses slowed down",
    "analysisworkerjobfailures": "Background analysis jobs kept failing",
    "highanalysisjobfailurerate": "Background analysis jobs kept failing",
    "targetdeploymentdown": "Tracked deployment went unreachable",
}

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/=]{8,}")
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}(?:\.[A-Za-z0-9_\-]{8,})?")
_SECRET_VALUE_RE = re.compile(
    r"(?i)(api[_-]?key|secret|password|passwd|pwd|token|private[_-]?key|"
    r"smtp[_-]?pass|gemini[_-]?api[_-]?key)\s*[:=]\s*['\"]?\S+"
)


def _redact_secrets(text: str) -> str:
    """Replace emails/JWTs/tokens/key material with '[redacted]'."""
    if not text:
        return text
    redacted = _EMAIL_RE.sub("[redacted]", text)
    redacted = _BEARER_RE.sub("Bearer [redacted]", redacted)
    redacted = _JWT_RE.sub("[redacted-jwt]", redacted)
    # Keep the key name for debuggability, hide only the value.
    def _mask_value(match: re.Match[str]) -> str:
        label = re.split(r"\s*[:=]\s*", match.group(0), maxsplit=1)[0]
        return f"{label}=[redacted]"
    return _SECRET_VALUE_RE.sub(_mask_value, redacted)


def _truncate(text: str, limit: int = _EXCERPT_LIMIT) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _humanize_alert(alert_name: str) -> str:
    """Map a technical alert name to a plain-language headline."""
    label = _ALERT_PLAIN_LABELS.get((alert_name or "").strip().lower())
    if label:
        return label
    # Fallback: split CamelCase / snake_case into plain words.
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", (alert_name or "unknown"))
    words = re.sub(r"[_\-]+", " ", words).strip().lower()
    return words or "an alert fired"


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
    """Fail-closed deterministic diagnosis (read-only flag always True).

    Human-readable History-tab fallback: plain-language summary naming the
    alert, most-likely cause plus what was checked, and a numbered
    human-runnable remediation plan shown as display text only.
    """
    safe_alert = (alert_name or "unknown").strip() or "unknown"
    safe_notes = _redact_secrets((context_notes or "no additional context").strip())
    safe_notes = _truncate(safe_notes, 300)
    plain = _humanize_alert(safe_alert)
    window = max(5, min(int(time_window_minutes or 30), 1440))
    excerpt = _truncate(
        f"Alert {safe_alert} fired within the last {window} min. "
        f"Context: {safe_notes}. Telemetry unavailable to the offline fallback.",
        _EXCERPT_LIMIT,
    )
    return OnCallDiagnosisOutput(
        incident_summary=(
            f"{plain} (alert {safe_alert}, last {window} minutes). "
            "Telemetry was unavailable, so this is a safe starting triage "
            "and no action was taken."
        ),
        root_cause_hypothesis=(
            "Most likely: background jobs timed out on a large repository or the "
            "tracked deployment returned errors. Checked: no live Prometheus, Loki, "
            "or Tempo data was available in offline mode, so this is unconfirmed "
            "and needs a human to review the dashboards and worker logs."
        ),
        confidence=0.25,
        evidence_citations=[
            TelemetryCitation(
                source="loki",
                query='{app="worker"} |= "ERROR"',
                excerpt=excerpt,
            )
        ],
        recommended_actions=[
            "1. Check worker logs for TimeoutError or out-of-memory lines around the alert window (read-only).",
            "2. Check the Prometheus error-rate and worker job failure dashboards for the same window.",
            "3. Check database pool usage and the analysis job queue depth before changing anything.",
            "4. Ask a human to approve any restart, scaling, or setting change — this diagnosis takes no action itself.",
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
        safe_notes = _redact_secrets((context_notes or "(none)")[:1000])
        plain_hint = _humanize_alert(alert_name)
        user = (
            f"ALERT: {alert_name} | plain meaning: {plain_hint} | window={window} minutes\n"
            f"Context notes: {safe_notes}\n\n"
            f"{_telemetry_to_text(metric_queries, log_streams, trace_summaries)}\n\n"
            "Write a History-tab diagnosis a non-expert can understand:\n"
            "- incident_summary: 1-2 plain sentences, no metric jargon "
            "(say 'API errors spiked', never '5xx share >5%'). Must name the alert "
            f"({alert_name}) and the window ({window} minutes).\n"
            "- root_cause_hypothesis: most-likely cause in plain words + one "
            "sentence on what telemetry was checked and what is still unknown.\n"
            "- confidence: lower it (<=0.5) when telemetry is missing or thin.\n"
            "- evidence_citations: only these sources: prometheus, loki, tempo, "
            "postgres_jobs; each with source/query/excerpt, excerpt under 500 chars.\n"
            "- recommended_actions: remediation plan of 3-5 numbered steps, plain "
            "verbs ('1. Check X', '2. Compare Y', '3. Ask a human to approve Z'), "
            "ordered by value, each runnable by a human, display text only — "
            "this agent takes no action itself.\n"
            "- read_only_verified=true. Redact emails/JWTs/tokens/keys to '[redacted]'."
        )
        return (ONCALL_SYSTEM, user)

    def _parse(raw: dict[str, Any]) -> OnCallDiagnosisOutput:
        # Enforce read-only flag and source allowlist regardless of model output.
        # Unknown sources are rejected (never silently coerced) so telemetry
        # citations stay auditable. Fail closed: any violation raises and the
        # caller falls back to the deterministic diagnosis.
        raw = dict(raw)
        raw["read_only_verified"] = True
        for key in ("incident_summary", "root_cause_hypothesis"):
            if isinstance(raw.get(key), str):
                raw[key] = _redact_secrets(raw[key])
        cleaned_actions: list[str] = []
        for step in raw.get("recommended_actions", []) or []:
            cleaned_actions.append(_redact_secrets(str(step))[:500])
        raw["recommended_actions"] = cleaned_actions
        citations = []
        for c in raw.get("evidence_citations", []) or []:
            if isinstance(c, dict) and c.get("source") not in _ALLOWED_SOURCES:
                raise ValueError(
                    f"Unknown telemetry source {c.get('source')!r}; allowed: "
                    f"{sorted(_ALLOWED_SOURCES)}"
                )
            if isinstance(c, dict):
                c = dict(c)
                if isinstance(c.get("query"), str):
                    c["query"] = _redact_secrets(c["query"])[:500]
                if isinstance(c.get("excerpt"), str):
                    c["excerpt"] = _truncate(_redact_secrets(c["excerpt"]))
            citations.append(c)
        raw["evidence_citations"] = citations
        return OnCallDiagnosisOutput.model_validate(raw)

    return run_with_fallback(
        prompt_builder=_prompt,
        response_schema=OnCallDiagnosisOutput,
        parse=_parse,
        fallback=lambda exc: fallback_diagnosis(alert_name, window, context_notes, exc),
    )


class OnCallAgent:
    """Protocol-compliant wrapper around :func:`diagnose_incident`.

    Queries read-only Prometheus/Loki/Tempo HTTP endpoints when reachable and
    passes the collected telemetry into :func:`diagnose_incident`. Never
    runs shell commands, database writes, or automatic fixes; the
    remediation plan is display text only.
    """

    def __init__(
        self,
        prometheus_url: str = "http://prometheus:9090",
        loki_url: str = "http://loki:3100",
        tempo_url: str = "http://tempo:3200",
    ) -> None:
        self.prometheus_url = prometheus_url.rstrip("/")
        self.loki_url = loki_url.rstrip("/")
        self.tempo_url = tempo_url.rstrip("/")

    def _fetch_readonly_telemetry(
        self, alert_name: str, time_window_minutes: int
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        metrics: list[dict[str, Any]] = []
        logs: list[dict[str, Any]] = []
        traces: list[dict[str, Any]] = []
        try:
            import httpx

            prom_query = (
                'sum(rate(http_requests_total{status=~"5.."}[5m]))'
                if "5xx" in alert_name.lower()
                else f"increase(analysis_runs_failed_total[{time_window_minutes}m])"
            )
            with httpx.Client(timeout=2.0) as client:
                try:
                    resp = client.get(
                        f"{self.prometheus_url}/api/v1/query",
                        params={"query": prom_query},
                    )
                    if resp.status_code == 200:
                        metrics.append(
                            {"query": prom_query, "result": resp.text[:400]}
                        )
                except Exception:
                    pass
                try:
                    loki_q = '{app=~"backend|worker"} |= "ERROR"'
                    resp = client.get(
                        f"{self.loki_url}/loki/api/v1/query_range",
                        params={"query": loki_q, "limit": 10},
                    )
                    if resp.status_code == 200:
                        logs.append(
                            {"query": loki_q, "excerpt": resp.text[:400]}
                        )
                except Exception:
                    pass
                try:
                    resp = client.get(
                        f"{self.tempo_url}/api/search",
                        params={"limit": 5},
                    )
                    if resp.status_code == 200:
                        traces.append(
                            {
                                "query": "tempo:/api/search?limit=5",
                                "excerpt": resp.text[:400],
                            }
                        )
                except Exception:
                    pass
        except Exception:
            pass
        return metrics, logs, traces

    def diagnose(
        self,
        alert_name: str,
        time_window_minutes: int = 30,
        context_notes: str | None = None,
    ) -> dict[str, Any]:
        metrics, logs, traces = self._fetch_readonly_telemetry(
            alert_name, time_window_minutes
        )
        output = diagnose_incident(
            alert_name=alert_name,
            time_window_minutes=time_window_minutes,
            context_notes=context_notes,
            metric_queries=metrics or None,
            log_streams=logs or None,
            trace_summaries=traces or None,
        )
        return output.model_dump()

