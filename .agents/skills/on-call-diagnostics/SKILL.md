---
name: on-call-diagnostics
description: >-
  Diagnose production or application incidents using the bounded, read-only
  On-Call Agent over Prometheus metrics, Loki logs, and Tempo traces. Use this
  skill when implementing or testing Phase 4 observability, user-impact alerts,
  or backend/app/agents/oncall_agent.py.
---

# Bounded Read-Only On-Call Diagnostics Skill

Use this workflow when building or invoking the Phase 4 On-Call Agent (`backend/app/agents/oncall_agent.py`) and user-impact alerts (`infra/prometheus/alert_rules.yml`).

## Steps

1. **Verify Read-Only Safety Boundary**:
   - The On-Call Agent may only query read-only observability endpoints (Prometheus `/api/v1/query`, Loki `/loki/api/v1/query_range`, Tempo trace summaries, and read-only PostgreSQL job status counts).
   - It must never execute shell commands, restart containers, or mutate database state.
2. **Correlate User-Impact SLIs**:
   - Inspect the firing alert (`HighHttp5xxErrorRate`, `HighApiLatencyP95`, `AnalysisWorkerJobFailures`, `TargetDeploymentDown`).
   - Collect matching log excerpts and error traces from the requested `time_window_minutes`.
3. **Return Structured Diagnosis**:
   - Populate `OnCallDiagnosisOutput` with `incident_summary`, `root_cause_hypothesis`, `confidence`, `evidence_citations`, `recommended_actions`, and `read_only_verified=True`.

