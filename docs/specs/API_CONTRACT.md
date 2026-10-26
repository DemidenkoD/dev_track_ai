# OpenAPI 3.1 REST Contract Specification

Base Path: `/api/v1`

All protected endpoints require `Authorization: Bearer <jwt_token>` obtained from `POST /api/v1/auth/login`.

---

## 1. Authentication & System Health

### `GET /api/v1/health`
Unauthenticated health endpoint for Docker/Nginx/Deployment checks.
- **Response `200 OK`**:
  ```json
  {
    "status": "ok",
    "version": "0.3.0",
    "database": "connected",
    "worker_status": "active"
  }
  ```

### `POST /api/v1/auth/login`
Authenticates the single predefined reviewer/developer account configured in `.env`.
- **Request Body (`LoginRequest`)**:
  ```json
  {
    "username": "reviewer@datatalks.club",
    "password": "devtrack-zoomcamp-2026"
  }
  ```
- **Response `200 OK` (`TokenResponse`)**:
  ```json
  {
    "access_token": "eyJhbGci...",
    "token_type": "bearer",
    "expires_in": 86400,
    "user": {
      "username": "reviewer@datatalks.club",
      "role": "reviewer"
    }
  }
  ```

### `GET /api/v1/auth/me`
Returns the current authenticated predefined user profile.

---

## 2. Rubrics & Rubric Ingestion

### `GET /api/v1/rubrics`
Lists available versioned rubrics (always includes the built-in **DataTalksClub AI Dev Tools Zoomcamp 2026** rubric).
- **Response `200 OK`**: `list[RubricSummarySchema]`

### `GET /api/v1/rubrics/{rubric_id}`
Returns full rubric details including all criteria, official scoring levels, point values, passing threshold, version, source URL, and retrieval date.
- **Response `200 OK`**: `RubricDetailSchema`

### `POST /api/v1/rubrics/ingest`
Ingests a new course rubric from a public URL, uploaded PDF/Markdown file, or raw pasted text using the **Rubric Analyst** agent.
- **Request Body (`RubricIngestRequest`)**:
  ```json
  {
    "title": "Custom Course Rubric",
    "course_name": "MLOps Zoomcamp",
    "source_type": "url",
    "source_url": "https://github.com/DataTalksClub/mlops-zoomcamp/blob/main/07-project/README.md",
    "raw_content": null
  }
  ```
- **Response `201 Created`**: `RubricDetailSchema`

---

## 3. Projects & Dashboard

### `GET /api/v1/dashboard`
Returns aggregated multi-project summary cards, upcoming deadlines, overall expected course scores (separated into `estimated_points` and `verified_points`), development completion percentages, security status badges, and deployment availability badges.
- **Response `200 OK`**: `DashboardOverviewSchema`

### `GET /api/v1/projects`
Lists all projects with optional `?status=active` filter.
- **Response `200 OK`**: `list[ProjectSummarySchema]`

### `POST /api/v1/projects`
Creates a new tracked project (validates that `github_repo_url` is a public GitHub repository) and generates initial draft assessment and development milestones from the selected rubric.
- **Request Body (`ProjectCreateRequest`)**:
  ```json
  {
    "name": "DevTrack AI",
    "description": "Course-first AI project mentor",
    "github_repo_url": "https://github.com/DataTalksClub/ai-dev-tools-zoomcamp",
    "course_name": "AI Dev Tools Zoomcamp 2026",
    "rubric_id": "uuid-of-builtin-rubric",
    "start_date": "2026-10-01",
    "target_date": "2026-11-15",
    "weekly_hours": 12,
    "diary_path": "docs/DIARY.md",
    "deployment_url": "https://devtrack.example.com",
    "daily_schedule_cron": "0 6 * * *"
  }
  ```
- **Response `201 Created`**: `ProjectDetailSchema`

### `GET /api/v1/projects/{project_id}`
Returns full project configuration, current progress metrics, and latest analysis summary.

### `PATCH /api/v1/projects/{project_id}`
Updates project status (`active`, `paused`, `archived`, `completed`), dates, `diary_path` override, `deployment_url` override, or schedule.

### `DELETE /api/v1/projects/{project_id}`
Deletes a project and its associated snapshots.

---

## 4. Assessment Milestones & Development Milestones

### `GET /api/v1/projects/{project_id}/milestones`
Returns both **Assessment Milestones** (official course criteria + max points) and nested **Development Milestones** (actionable tasks), along with `milestones_approved` status.
- **Response `200 OK`**: `ProjectMilestonesResponse`

### `POST /api/v1/projects/{project_id}/milestones/approve`
Approves generated milestones so they become active for progress tracking.
- **Request Body (`MilestoneApprovalRequest`)**:
  ```json
  {
    "approve_all": true,
    "assessment_milestone_ids": [],
    "development_milestone_ids": []
  }
  ```

### `POST /api/v1/projects/{project_id}/development-milestones`
Creates a new development milestone linked to an `assessment_milestone_id`.

### `PATCH /api/v1/projects/{project_id}/development-milestones/{dev_milestone_id}`
Updates a development milestone's status (`outstanding`, `partial`, `completed`), title, or effort estimate. Note: Completing all development milestones under an assessment criterion **never** automatically modifies the official criterion score.

---

## 5. Analysis Runs & One-Time Notifications

### `POST /api/v1/projects/{project_id}/analyses`
Triggers a manual analysis run (or initial analysis) queued in PostgreSQL (`analysis_runs`). Accepts an optional **one-time email notification** address held strictly in volatile memory.
- **Request Body (`TriggerAnalysisRequest`)**:
  ```json
  {
    "notify_email_once": "developer@example.com",
    "acknowledge_ephemeral_email": true
  }
  ```
  *Privacy Constraint:* `notify_email_once` is **never** written to PostgreSQL, application logs, or OpenTelemetry spans. It is stored in an in-memory map `EPHEMERAL_NOTIFICATIONS[analysis_run_id]` and deleted immediately after the completion email is sent.
- **Response `202 Accepted`**: `AnalysisRunSchema`

### `GET /api/v1/projects/{project_id}/analyses`
Lists historical analysis runs with their recorded `commit_sha`, `estimated_total_points`, `verified_total_points`, and `dev_completion_pct`.

### `GET /api/v1/projects/{project_id}/analyses/{analysis_run_id}`
Returns full details of a specific analysis snapshot.

---

## 6. Scorecard, Human Overrides & Evidence Explorer

### `GET /api/v1/projects/{project_id}/scorecard`
Returns the latest (or `?analysis_run_id=...` historical) 12-criterion scorecard with:
- Official scoring level descriptions
- `ai_proposed_points`, `ai_reasoning`, `ai_confidence`
- `score_state` (`estimated`, `verified`, `needs_review`)
- `human_override_points`, `human_override_reason`
- `effective_points`
- Linked `evidence_items`
- Potential additional points and `missing_for_next_level`
- Explicit banner reminder that AI estimates are advisory, not official course grades.

### `PATCH /api/v1/projects/{project_id}/scorecard/{criterion_assessment_id}`
Allows a human reviewer or user to override a proposed score or change `score_state` to `verified` / `needs_review` while retaining the original `ai_proposed_points` and `ai_reasoning` for side-by-side comparison.
- **Request Body (`ScoreOverrideRequest`)**:
  ```json
  {
    "score_state": "verified",
    "human_override_points": 2,
    "human_override_reason": "Verified single-command Docker Compose startup on clean VM."
  }
  ```

### `GET /api/v1/projects/{project_id}/evidence`
Queries collected evidence items across commits, source files, README/docs, GitHub Actions workflows, tests, deployment checks, observability configs, and security reports. Supports `?evidence_type=` and `?analysis_run_id=` filters.

---

## 7. Recommendations, Diary, Security & Deployment Modules

### `GET /api/v1/projects/{project_id}/recommendations`
Returns prioritized high-ROI next actions from the **AI Project Mentor**, ordered by priority rank (`suggested_task`, `related_criterion_code`, `potential_points_delta`, `priority`, `supporting_evidence`, `estimated_effort_hours`, `technical_risk`).

### `GET /api/v1/projects/{project_id}/diary`
Returns the latest **Diary Analyst** snapshot (`discovered_path`, `completed_work`, `blockers`, `decisions`, `next_steps`, `git_alignment_summary`, and `discrepancies` between diary claims and actual Git commits).

### `GET /api/v1/projects/{project_id}/security`
Returns the latest **Security Reviewer** report combining deterministic findings from Semgrep, Gitleaks, `pip-audit`, `npm audit`, and Bandit with Gemini explanations and remediation guidance.

### `GET /api/v1/projects/{project_id}/deployments`
Returns deployment discovery sources, availability history, HTTP status codes, HTTPS validity, and response times (in ms).

### `POST /api/v1/projects/{project_id}/deployments/check`
Triggers an immediate SSRF-protected HTTPX health check against the project's deployment URL.

---

## 8. Bounded Read-Only On-Call Agent (Phase 4) + History Tab (Phase 4b)

### `POST /api/v1/oncall/diagnose`
Invokes the bounded, read-only **On-Call Agent** to inspect Prometheus metrics, Loki logs, Tempo traces, and recent failure alerts, returning a structured root-cause diagnosis and safe remediation runbook.
- **Request Body (`OnCallDiagnoseRequest`)**:
  ```json
  {
    "alert_name": "HighAnalysisJobFailureRate",
    "time_window_minutes": 30,
    "context_notes": "Worker jobs timing out on large repositories"
  }
  ```
- **Response `200 OK` (`OnCallDiagnosisResponse`)**:
  ```json
  {
    "incident_summary": "...",
    "root_cause_hypothesis": "...",
    "confidence": 0.88,
    "evidence_citations": [
      {"source": "loki", "query": "{app=\"worker\"} |= \"TimeoutError\"", "excerpt": "..."}
    ],
    "recommended_actions": [
      "Increase ANALYSIS_TIMEOUT_SECONDS or enforce shallow git clone --depth 50"
    ],
    "read_only_verified": true
  }
  ```
  Kept for backwards compatibility; the History tab below replaces manual `alert_name` typing.

### `POST /api/v1/oncall/webhook`
Alertmanager native webhook receiver — persists alerts as history rows with a remediation plan. **No user JWT**; authenticates via shared secret `Authorization: Bearer <ALERTMANAGER_WEBHOOK_SECRET>` or `X-Alertmanager-Secret` header (`401` otherwise).
- **Request Body (`AlertmanagerWebhookPayload`)**:
  ```json
  {
    "receiver": "devtrack-oncall",
    "status": "firing",
    "alerts": [
      {
        "status": "firing",
        "labels": {"alertname": "HighHttp5xxErrorRate", "severity": "critical", "service": "api"},
        "annotations": {"summary": "5xx spike", "description": "...", "runbook": "..."},
        "startsAt": "2026-10-26T10:00:00.000Z",
        "endsAt": null,
        "fingerprint": "abc123"
      }
    ]
  }
  ```
- **Behavior**: dedupes on `(fingerprint, startsAt)` (existing row is updated, not duplicated); creates rows with `status=firing|resolved`; invokes the on-call agent synchronously via protocol to fill `diagnosis_json`; redacts emails/JWTs/secrets from `alert_payload_json` before persistence.
- **Response `202 Accepted` (`OnCallWebhookResponse`)**: `{ "incidents": [OnCallIncidentSchema, ...] }`

### `GET /api/v1/oncall/incidents`
Lists persisted incidents for the History tab (auth required). Supports `?status=firing|acknowledged|resolved`, `?limit=` (1–200, default 50), and optional `?project_id=<uuid>` (project-scoped view when present; global cross-project view when omitted — backward-compatible), newest first.
- **Response `200 OK`**: `list[OnCallIncidentSchema]`
- **Security-scanner bridge:** critical/high scanner findings are linked into this History view by Track 3's `_persist_security_report`, which calls Track 1's stable creator `create_security_incident(db, project_id, rule_id, severity, file_path, commit_sha, summary, remediation_hints)` (Track 1 owns the creator; Track 3 only imports and calls it — do NOT reimplement the call here). Bridge rows use `alert_name="SecurityCritical:{rule_id}"`, `severity` passthrough (`critical`|`high`), `service="security-scanner"`, `fingerprint=sha256(rule_id|file_path|commit_sha)hex[0:32]`, `project_id=<real project uuid>`, `status=firing`, `diagnosis_json` built from the Security Reviewer summary (`incident_summary`, `root_cause_hypothesis`, `confidence=0.75`, `evidence_citations=[{source:"security-scanner", query:rule_id, excerpt:file_path}]`, `recommended_actions=[hints]`, `read_only_verified=true`). Dedupe on `fingerprint` alone within the same `project_id`+`commit_sha` (return existing instead of duplicate). Payloads are redacted of emails/JWTs/secrets before persistence; webhook behavior is unchanged (infra alerts still persist with `project_id=None`).

### `GET /api/v1/oncall/incidents/{incident_id}`
Returns a single incident with its redacted payload and full diagnosis/remediation plan (auth required).
- **Response `200 OK`**: `OnCallIncidentDetailSchema` (`OnCallIncidentSchema` + `alert_payload_json` + `diagnosis: OnCallDiagnosisResponse`)

### `POST /api/v1/oncall/incidents/{incident_id}/acknowledge`
Marks an incident `acknowledged` with an optional human note (auth required).
- **Request Body (`AcknowledgeRequest`)**: `{ "note": "Investigating 5xx spike" }`
- **Response `200 OK`**: `OnCallIncidentDetailSchema`

