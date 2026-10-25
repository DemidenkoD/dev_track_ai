# DevTrack AI — Product Specification v0.4

> **Tagline:** Your AI mentor from project idea to deployment.
> **Docs:** [README](../README.md) · [Problem Description](PROBLEM_DESCRIPTION.md) · [API Contract](specs/API_CONTRACT.md) · [Database Schema](specs/DATABASE_SCHEMA.md) · [Agent Team](specs/AGENT_TEAM_SPEC.md) · [Built-in Rubric](rubrics/ai_dev_tools_zoomcamp_2026.json)
> **Tracker (public):** https://github.com/users/DemidenkoD/projects/4/views/1

> **Advisory notice (read first):** DevTrack AI is an **advisory, read-only mentor**. All point values it produces are **AI estimates, never official course grades**. Every scorecard view and API response MUST distinguish official rubric criteria from AI-generated recommendations and display the banner *"AI estimates are advisory, not official grades."* See §4 score states.

## 1. Problem & Users

Full context: [docs/PROBLEM_DESCRIPTION.md](PROBLEM_DESCRIPTION.md).

**Core problem (5 failure modes):** (1) rubric misalignment — polishing zero-point features while missing passing criteria (single-command startup, PR test triggers); (2) subjective self-assessment vs. verifiable evidence; (3) stalled momentum & scope creep without rubric-linked checkpoints; (4) unnoticed security/deployment regressions (leaked secrets, vulnerable deps, broken health endpoints, expired TLS); (5) fragmented tracking across rubric pages, commits, diaries, and live health.

**What DevTrack AI answers:** (1) Am I meeting course requirements? (2) How many points could I currently receive? (3) What blocks more points? (4) What next? (5) Is my app secure and deployed?

**Primary users:** DataTalksClub AI Dev Tools Zoomcamp 2026 participants. **Secondary:** portfolio builders, cohort reviewers verifying evidence. **Impact:** higher completion rates, zero leaked secrets at submission, evidence-backed self-assessment before peer grading.

**Product invariants (non-negotiable):**
- Advisory & read-only only: never pushes commits, opens PRs, or modifies user repos.
- Never present AI estimates as official grades (`score_state` + banner, §4).
- Two separate milestone/progress dimensions: **Assessment** (official points) vs. **Development** (actionable tasks). Completing dev tasks **never auto-awards** assessment points.
- Zero persistent email storage (§5).

**Built-in rubric:** DataTalksClub AI Dev Tools Zoomcamp 2026 — 12 criteria, 24 max points, 10/24 to pass. Source: https://github.com/DataTalksClub/ai-dev-tools-zoomcamp/tree/main/project. Versioned (`2026.1.0`); updates create a new row, never mutate existing assessments.

| # | Criterion (`code`) | Max |
|---|---|---:|
| 1 | Problem Description (`problem_description`) | 2 |
| 2 | Product Specification (`product_specification`) | 2 |
| 3 | Agent Team Specification (`agent_team_specification`) | 2 |
| 4 | Context Management (`context_management`) | 2 |
| 5 | Application (`application`) | 2 |
| 6 | Testing (`testing`) | 2 |
| 7 | Containerization (`containerization`) | 2 |
| 8 | Deployment (`deployment`) | 2 |
| 9 | CI/CD (`ci_cd`) | 3 |
| 10 | Observability (`observability`) | 2 |
| 11 | Alerting on User Impact (`alerting_on_user_impact`) | 1 |
| 12 | On-Call Agent (`on_call_agent`) | 2 |
| | **Total** | **24** |

Each criterion is scored only against its official `scoring_levels` (e.g. CI/CD 0–3, Application 0–2 as published); invented scoring rules are forbidden.

## 2. Features (F1–F8) + Non-goals

- **F1 — Projects & dashboard** (`GET /api/v1/projects`, `GET /api/v1/dashboard`): single predefined reviewer account (no public registration), multiple projects per account (`active|paused|archived|completed`), cards for dev completion %, estimated vs. verified points, deadlines, security/deployment badges.
- **F2 — Rubric ingestion & versioning** (`GET/POST /api/v1/rubrics*`): ingest from public URL / PDF / Markdown / raw text via Rubric Analyst; immutable versioned `rubrics` + `rubric_criteria` rows retaining source URL, version, `retrieved_at`, `max_points`, `passing_threshold`.
- **F3 — Two-tier milestones** (`GET /api/v1/projects/{id}/milestones`, `…/approve`, `…/development-milestones*`): AI-drafted **Assessment Milestones** (official criteria + max points, `is_approved` gate, `milestones_approved`) decomposed into **Development Milestones** (`outstanding|partial|completed`, `ai_generated|user_created`). Approval required before tracking.
- **F4 — Evidence-backed scorecard & human overrides** (`…/scorecard*`, `…/evidence`): 12-criterion scorecard with official levels, `ai_proposed_points`, `ai_reasoning`, `ai_confidence`, `score_state`, `human_override_points/reason`, `effective_points`, `evidence_ids`, `missing_for_next_level`. Overrides preserve originals side-by-side.
- **F5 — Daily + manual analysis & mentor recommendations** (`…/analyses*`, `…/recommendations`): PostgreSQL-backed `analysis_runs` queue (`initial|daily|manual`, `queued|running|completed|failed`), commit-SHA snapshots (`commit_sha`, `previous_commit_sha`), stalled/scope-creep flags, high-ROI ranked recommendations (`potential_points_delta`, `priority`, `estimated_effort_hours`, `technical_risk`).
- **F6 — Development diary analyst** (`…/diary`): auto-discover common diary paths with manual `diary_path` override; extract completed work / blockers / decisions / next steps; cross-check claims vs. Git history with `discrepancies[]`.
- **F7 — Security reviewer (deterministic + Gemini)** (`…/security`): Semgrep, Gitleaks, `pip-audit`, `npm audit`, Bandit in isolated subprocesses with timeouts; Gemini explains, deduplicates, ranks remediation; secrets redacted.
- **F8 — Deployment monitor, one-time notifications & bounded on-call** (`…/deployments*`, `POST /api/v1/oncall/diagnose`): SSRF-safe httpx checks (status, HTTPS validity, latency, availability history; sources `readme|config|manual`); optional one-time email (ephemeral, §5); Phase 4 read-only on-call diagnosis over Prometheus/Loki/Tempo with `read_only_verified`.

**Non-goals (explicitly out of scope):** auto-editing user repositories / opening PRs; private-repo access; persistent email subscriptions; presenting AI estimates as official grades; dev-task completion auto-awarding assessment points; executing untrusted repo scripts; storing secrets or emails in DB/logs/traces.

## 3. Architecture

**Request path:** `React + TypeScript (Vite)` → `FastAPI /api/v1` (JWT `POST /api/v1/auth/login`) → `PostgreSQL + SQLAlchemy 2.0` + `PostgreSQL-backed worker` (poll `analysis_runs`, `WORKER_POLL_INTERVAL_SECONDS`, `ANALYSIS_TIMEOUT_SECONDS`, `MAX_REPO_SIZE_MB`). Health: `GET /api/v1/health` → `{status, version, database, worker_status}`. Single-command local boot: `make up` (`docker compose up --build -d`); frontend `:5173`, API docs `:8000/docs`, Prometheus `:9090`, Grafana `:3000`.

**Runtime AI agents** (`backend/app/agents/`, official `google-genai` SDK, `from google import genai`): every LLM call enforces **structured output** via `types.GenerateContentConfig(response_mime_type="application/json", response_schema=<Pydantic model in backend/app/schemas/agent_outputs.py>)`. Model from `GEMINI_MODEL` (default `gemma-4-31b-it` per `.env.example` / `backend/app/agents/base.py:DEFAULT_GEMINI_MODEL`); key from `GEMINI_API_KEY` (never logged/committed). No agent mutates external repos.

| # | Runtime agent (module) | Structured output (`response_schema`) | Responsibility |
|---|---|---|---|
| 1 | Project Mentor / Orchestrator (`project_mentor.py`) | `MentorEvaluationOutput` | Synthesize services/agents; detect stalled/scope-creep vs. `previous_commit_sha`; ranked `Recommendations` |
| 2 | Rubric Analyst (`rubric_analyst.py`) | `ExtractedRubricOutput` / `ScorecardEvaluationOutput` | Extract criteria/levels/thresholds; score evidence vs. official levels (`ai_proposed_points`, `ai_confidence`, `score_state`, `evidence_ids`) |
| 3 | Progress Analyst (`progress_analyst.py`) | `ProgressEvaluationOutput` | **Development Completion** (`completed|partial|outstanding`, deadlines) independently from **Expected Course Score** (`estimated|verified|potential`) |
| 4 | Diary Analyst (`diary_analyst.py`) | `DiaryAnalysisOutput` | Extract work/blockers/decisions/next steps; git-alignment + discrepancies |
| 5 | Security Reviewer (`security_reviewer.py`) | `SecurityReviewOutput` | Explain/dedupe deterministic findings; course-context exploitability; ranked remediation |
| 6 | Bounded On-Call Agent, Phase 4 (`oncall_agent.py`) | `OnCallDiagnosisOutput` | Read-only Prometheus/Loki/Tempo diagnosis; evidence citations; human-approved runbook |

**Deterministic services** (`backend/app/services/`): `github_service` (read-only REST + shallow isolated clone), `security_scanner` (runner), `deployment_monitor` (SSRF-safe httpx), `notification_service` (ephemeral SMTP), `diary_service`, `rubric_service`. API layer calls services via clean protocols so tracks develop against mocks (see `docs/specs/AGENT_TEAM_SPEC.md`).

## 4. Data Model (mirrors `docs/specs/DATABASE_SCHEMA.md` + `backend/app/models/`)

Source of truth: `docs/specs/DATABASE_SCHEMA.md`; REST mirror: `docs/specs/API_CONTRACT.md`.

- **Rubrics & criteria:** `rubrics` (slug, title, course, `source_type=builtin|url|pdf|markdown|text`, `source_url`, `raw_content`, `version`, `retrieved_at`, `is_official`, `max_points=24`, `passing_threshold=10`) → `rubric_criteria` (code, name, description, `display_order`, `max_points`, `scoring_levels[]`, `required_evidence_types[]`). Immutable versioning.
- **Projects:** `projects` (name, description, `github_repo_url` + parsed owner/repo, `default_branch=main`, course, `rubric_id`, `status`, start/target dates, `weekly_hours`, `diary_path`, `deployment_url`, `daily_schedule_cron='0 6 * * *'`, `milestones_approved`, `last_analysis_at`).
- **Milestones:** `assessment_milestones` (project + `rubric_criterion_id`, title, `max_points`, `is_approved`) → `development_milestones` (title, description, `status=outstanding|partial|completed`, `source=ai_generated|user_created`, `is_approved`, due/effort/completed_at). **Dev completion never auto-awards assessment points.**
- **Analysis runs:** `analysis_runs` (per-project job record: `trigger_type`, `status`, `commit_sha` + `previous_commit_sha`, `estimated_total_points`, `verified_total_points`, `max_total_points=24`, `dev_completion_pct`, `summary_markdown`, `stalled_flag`, `scope_creep_flag`, error + timestamps).
- **Evidence → assessments:** `evidence_items` (`evidence_type`: `commit|source_file|readme|documentation|ci_workflow|test_result|docker_compose|deployment_url|observability_config|security_report|agent_config|diary_entry`; title, `path_or_url`, commit, bounded `snippet`, `metadata_json`) linked from `criterion_assessments` (`assessment_milestone_id`, `criterion_code`, `max_points`, **`ai_proposed_points` + `ai_reasoning` (immutable, always preserved)**, `ai_confidence 0–1`, `missing_for_next_level`, **`score_state=estimated|verified|needs_review`**, `human_override_points/reason/overridden_at`, `evidence_ids[]`). `effective_points = human_override_points if not None else ai_proposed_points`.
- **Diary / security / deployment / recommendations:** `diary_snapshots` (discovered path, completed/blockers/decisions/next-steps, `git_alignment_summary`, `discrepancies[]`); `security_reports` (`pass|warning|critical`, `scanners_executed`, `ai_executive_summary`) → `security_findings` (scanner, rule, `info|low|medium|high|critical`, file/line, redacted `raw_message`, `ai_explanation/remediation`, `priority_rank`); `deployment_checks` (target URL, `discovery_source=readme|config|manual`, reachability, status, `https_valid`, `response_time_ms`); `recommendations` (rank, task, rationale, `related_criterion_code`, `potential_points_delta`, `critical|high|medium|low`, effort, `low|medium|high` risk, `supporting_evidence_ids[]`).
- **Zero-email invariant:** no `notification_email` column exists anywhere. `notify_email_once` lives only in volatile `EPHEMERAL_NOTIFICATIONS[analysis_run_id]` and is popped/deleted on send or failure — never in Postgres, logs, or traces.

## 5. Security & Privacy

- **Public-GitHub-only + SSRF protection:** only `https://github.com/<owner>/<repo>` accepted (validated on `POST /api/v1/projects`); read-only REST + shallow isolated clones; deployment checks via SSRF-safe `httpx` — resolve + validate IPs, block private/loopback/link-local/cloud-metadata ranges, allow only public HTTP/HTTPS, enforce timeouts.
- **Isolated deterministic scanners:** Semgrep, Gitleaks, `pip-audit`, `npm audit`, Bandit run in isolated subprocesses with strict timeouts/resource caps (`ANALYSIS_TIMEOUT_SECONDS`, `MAX_REPO_SIZE_MB`); never execute untrusted repo scripts; redact secret values from findings/logs.
- **Auth & secrets:** single predefined account; JWT (`Authorization: Bearer`, `ACCESS_TOKEN_EXPIRE_MINUTES=1440`); credentials via `.env` (`ADMIN_USERNAME/ADMIN_PASSWORD`, `SECRET_KEY`); never print/log/commit `GEMINI_API_KEY`, `MAIL_SMTP_PASS`, `SECRET_KEY`.
- **Ephemeral notifications:** `POST …/analyses {notify_email_once, acknowledge_ephemeral_email:true}` — address held strictly in process memory (`EPHEMERAL_NOTIFICATIONS[analysis_run_id]`), `.pop()`-ed immediately after send/failure; lost on restart by design; explicit one-time disclosure in UI/API.
- **Transport & least exposure:** HTTPS via reverse proxy in prod; bounded evidence `snippet`s; no sensitive data in OpenTelemetry spans/metrics; resource-limited worker jobs.

## 6. Acceptance Criteria (AC1–AC6, single-command verifiable)

- **AC1 — Spec completeness (closes `product_specification` 1→2):** `ls docs/PRODUCT_SPEC.md` exists and contains all five pillars — §2 Features (F1–F8 + non-goals), §3 Architecture (React→FastAPI `/api/v1`→Postgres+worker + 6-agent table with `MentorEvaluationOutput` etc. + `response_schema` + `GEMINI_MODEL` default), §4 Data Model (all entity groups + `ai_proposed/ai_reasoning`/`effective_points` + `score_state` + dev-never-auto-awards + zero-email invariant), §5 Security & Privacy, §6 this AC list — plus the advisory banner. *Verify: `ls docs/PRODUCT_SPEC.md && grep -c -e '^## [1-6]\.' docs/PRODUCT_SPEC.md` → `6`.*
- **AC2 — Problem linkage (supports `problem_description` 1→2):** §1 traces the 5 failure modes from `docs/PROBLEM_DESCRIPTION.md` to the 5 mentor questions, users, and the 12-criterion / 24-point / 10-pass table. *Verify: `grep -c -e 'problem_description\|product_specification\|Blind Spot' docs/PRODUCT_SPEC.md docs/PROBLEM_DESCRIPTION.md`.*
- **AC3 — Single-command boot:** `make up` (or `docker compose up --build -d`) starts frontend, backend, worker, db; `GET /api/v1/health` returns `{"status":"ok",…}`. *Verify: `make up && curl -s localhost:8000/api/v1/health`.*
- **AC4 — Single-command tests:** `pytest backend/tests -q -k "rubric or agent" | tail -2` passes (rubric/agent suites green). *Verify: `pytest backend/tests -q -k "rubric or agent" | tail -2`.*
- **AC5 — Contract/schema fidelity:** no drift between this spec and the locked contracts — criterion codes/points match `docs/rubrics/ai_dev_tools_zoomcamp_2026.json`, tables match `docs/specs/DATABASE_SCHEMA.md`, endpoints match `docs/specs/API_CONTRACT.md`. *Verify: `grep -c 'ai_proposed_points' docs/PRODUCT_SPEC.md docs/specs/DATABASE_SCHEMA.md docs/specs/API_CONTRACT.md` (all nonzero) `&& docker compose config -q`.*
- **AC6 — No-secret / invariant hygiene:** no secret values committed; `ai_proposed_points` + `ai_reasoning` preservation, `score_state estimated|verified|needs_review`, dev-never-auto-awards, and zero persistent email storage are all stated. *Verify: `grep -E -c 'ai_proposed_points|score_state|never auto-award|EPHEMERAL_NOTIFICATIONS' docs/PRODUCT_SPEC.md` (≥4) `&& ! grep -R -e 'your_gemini_api_key_here' --include='.env' . 2>/dev/null; grep -R -i -e 'GEMINI_API_KEY=' .env.example | head -1` (template placeholder only).*
