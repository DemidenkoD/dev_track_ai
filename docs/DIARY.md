# DevTrack AI — Engineering Diary & Architectural Evolution

> **Project:** DevTrack AI ("Your AI mentor from project idea to deployment")  
> **Course Rubric:** DataTalksClub AI Dev Tools Zoomcamp 2026 (12 Criteria, 24 Points)  
> **Repository:** `https://github.com/DemidenkoD/dev_track_ai`  
> **Live Deployment:** `https://ct-academia.pl`

---

## Overview & Development Methodology

DevTrack AI was engineered using a disciplined, multi-agent development methodology designed to achieve 100% compliance with the 12-criterion DataTalksClub AI Dev Tools Zoomcamp 2026 rubric. The system serves as an advisory, read-only AI mentor that inspects public GitHub repositories, developer diaries, deterministic security scan results, and live deployments to provide continuous, actionable feedback to course students.

Development was organized into four distinct chronological phases, governed by strict parallel file-ownership boundaries and domain invariants.

---

## Phase 1: Problem Formulation & Multi-Agent Architecture

### Context & Problem Framing
Technical course participants frequently fail or drop out due to five recurrent failure modes:
1. **Requirements Blindspot:** Submitting projects missing critical rubric sections (e.g., containerization or observability) despite functional code.
2. **Silent Degradation:** Broken builds, unpinned dependencies, or expired endpoints going unnoticed until final grading.
3. **Premature Optimization & Last-Minute Rushing:** Spending days polishing non-rubric features while missing baseline passing criteria.
4. **False Confidence:** Relying on unverified self-assessments or vague chat assistant feedback without grounding in actual repository artifacts.
5. **Unverifiable Demos:** Missing live deployment URLs, absent reviewer credentials, or unreachable health probes.

DevTrack AI was designed to systematically eliminate these failure modes by providing continuous, evidence-grounded rubric evaluations without ever modifying user repositories.

### Completed Work
- Defined the core product problem and audience analysis in `docs/PROBLEM_DESCRIPTION.md`.
- Specified the complete system capabilities, data entities, and workflows in `docs/PRODUCT_SPEC.md` v0.4.
- Architected the dual-layer agent system:
  1. **Development Agent Team:** Six specialized, non-overlapping development tracks (`backend-core-agent`, `ai-agents-specialist`, `integrations-worker-agent`, `frontend-ui-agent`, `qa-testing-agent`, `devops-observability-agent`) defined in `docs/specs/AGENT_TEAM_SPEC.md` and `.agents/agents/`.
  2. **Runtime Gemini Agents:** Six autonomous runtime agents (`RubricAnalyst`, `ProgressAnalyst`, `DiaryAnalyst`, `SecurityReviewer`, `ProjectMentor`, and `OnCallAgent`) located in `backend/app/agents/`.
- Established root and scoped context-management rule files (`AGENTS.md`, `backend/AGENTS.md`, `backend/app/agents/AGENTS.md`, `frontend/AGENTS.md`, and `infra/AGENTS.md`).
- Designed modular on-demand agent skills in `.agents/skills/` (`api-contract-sync`, `db-migrations`, `rubric-evaluation`, `security-scanners`, `on-call-diagnostics`).

### Decisions
- **Decision 1.1 (Read-Only Advisory Principle):** DevTrack AI must never push commits, create pull requests, or alter student code. It evaluates and advises only.
- **Decision 1.2 (Strict Ownership Boundaries):** Partitioned the codebase into 6 strict tracks to enable simultaneous parallel development by autonomous agents with zero file conflicts or merge overwrites.
- **Decision 1.3 (Explicit Score States):** Every criterion assessment must maintain an explicit `score_state`: `estimated`, `verified`, or `needs_review`. AI estimates must never be presented as official course grades.
- **Decision 1.4 (Human Overrides with History):** When a human reviewer overrides a criterion score (`human_override_points`), the original `ai_proposed_points` and `ai_reasoning` must remain preserved and visible.

### Blockers
- **Blocker 1.1:** Risk of multi-agent collision and context thrashing when multiple sub-agents edit shared modules simultaneously.  
  *Resolution:* Implemented strict directory boundaries codified in `AGENTS.md` and `docs/specs/AGENT_TEAM_SPEC.md`, prohibiting agents from modifying files outside their assigned track.
- **Blocker 1.2:** Context window saturation when passing entire repositories to LLMs.  
  *Resolution:* Formatted repository evidence extraction into structured bundles containing file paths, line numbers, doc excerpts, and git commit summaries.

### Next Steps
- Implement PostgreSQL database schema, SQLAlchemy 2.0 ORM models, and locked OpenAPI 3.1 REST contracts.
- Implement SSRF-safe deployment prober and deterministic security scanners.

---

## Phase 2: Data Model, REST Contracts & Security Hardening

### Context & Implementation
Phase 2 established the core data persistence layer, API schemas, and security architecture required for deterministic evaluation and safe multi-tenant operation.

### Completed Work
- Implemented PostgreSQL 16 data models via SQLAlchemy 2.0 async/sync ORM in `backend/app/models/` (`Project`, `AnalysisRun`, `CriterionAssessment`, `DevelopmentMilestone`, `AssessmentMilestone`, `DiarySnapshot`, `SecurityReport`, `SecurityFinding`, `DeploymentHealthCheck`, `IncidentDiagnosis`).
- Created versioned database migration scripts and built-in rubric seeders for the 12 criteria of the Zoomcamp 2026 scorecard (`backend/app/db/init_db.py`).
- Locked the OpenAPI 3.1 REST contract in `docs/specs/API_CONTRACT.md` and implemented corresponding Pydantic v2 validation models in `backend/app/schemas/`.
- Integrated five deterministic security scanners (`semgrep`, `gitleaks`, `bandit`, `pip-audit`, `npm-audit`) executing in isolated subprocesses with strict execution timeouts in `backend/app/services/security_scanner.py`.
- Implemented SSRF-hardened HTTP client routines in `backend/app/services/deployment_monitor.py` verifying resolved IP addresses against loopback, private RFC1918, link-local, and cloud metadata ranges before dispatching requests.
- Implemented the ephemeral notification worker with strict zero persistent email storage.

### Decisions
- **Decision 2.1 (Zero Persistent Email Storage):** Optional one-time email notifications (`notify_email_once`) must never be saved in PostgreSQL, printed in logs, or sent in OpenTelemetry traces. They reside strictly in volatile memory during analysis execution and are wiped immediately upon dispatch.
- **Decision 2.2 (Deterministic Subprocess Scanning):** Run static analysis and secret detection tools (`semgrep`, `gitleaks`) deterministically locally rather than relying solely on LLM code reviews, ensuring reproducible security findings.
- **Decision 2.3 (Dual Progress Dimensions):** Maintained two distinct progress dimensions: **Development Progress** (actionable task completion) and **Expected Course Score** (rubric criteria points). Completing development tasks never automatically awards course points without evidence.

### Blockers
- **Blocker 2.1:** Accidental leakage of user email addresses in FastAPI access logs and OpenTelemetry spans.  
  *Resolution:* Implemented custom logging filters and telemetry middleware in `backend/app/core/telemetry.py` that scrub email regex patterns, authorization headers, and API keys before emission.
- **Blocker 2.2:** Server-Side Request Forgery (SSRF) vulnerability when inspecting user-provided deployment URLs.  
  *Resolution:* Built an IP pre-resolution gate in `backend/app/services/deployment_monitor.py` that resolves DNS hostnames and rejects private (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), loopback (127.0.0.0/8), link-local (169.254.0.0/16), and cloud metadata endpoints (169.254.169.254) prior to HTTP connection.

### Next Steps
- Build the multi-provider AI evaluation engine with Google Gemini and resilient offline fallbacks.
- Develop the single-page application frontend dashboard with live polling and rich evidence display.

---

## Phase 3: Multi-Provider AI Fallback & Rubric Scorecard Engine

### Context & Implementation
Phase 3 wired the intelligent evaluation agents that interpret repository evidence, synthesize development diaries, review security scan outputs, and score course rubric criteria.

### Completed Work
- Integrated the official Google GenAI SDK (`google-genai`) supporting Gemini 2.5 Flash / Gemini Pro for structured output generation in `backend/app/agents/base.py`.
- Built multi-provider resiliency fallbacks supporting OpenCode, GLM, and deterministic rule-based evaluation when external API keys are unavailable or rate-limited.
- Implemented `RubricAnalyst` (`backend/app/agents/rubric_analyst.py`) with evidence-grounding guards (`_apply_evidence_grounding`) preventing hallucinations on empty or unverified repositories.
- Implemented `DiaryAnalyst` (`backend/app/agents/diary_analyst.py`) cross-referencing markdown diary claims against git commit history to detect alignment and report discrepancies.
- Implemented `SecurityReviewer` (`backend/app/agents/security_reviewer.py`) synthesizing raw scanner JSON outputs into prioritized executive summaries with concrete remediation guidance.
- Implemented `ProjectMentor` (`backend/app/agents/project_mentor.py`) generating prioritized, effort-estimated implementation tasks targeting remaining rubric gaps.
- Built the React 19 + TypeScript + Vite + Tailwind CSS frontend dashboard (`frontend/src/`) featuring live analysis polling, dual progress rings, interactive scorecard with human override controls, and multi-tab evidence inspectors.

### Decisions
- **Decision 3.1 (Evidence Grounding Over Generative Hallucination):** If specific evidence files required for a rubric criterion are absent in the repository checkout, the scorecard automatically caps the criterion score and marks it `needs_review`, preventing inflated ratings.
- **Decision 3.2 (Graceful Degradation):** The entire evaluation pipeline must execute deterministically without error even when `GEMINI_API_KEY` is not configured, falling back to rule-based analysis and heuristic diary parsing.
- **Decision 3.3 (Live Status Polling):** The frontend polls the backend analysis run endpoint every 4 seconds during `queued` or `running` states, updating the UI smoothly without manual page refreshes.

### Blockers
- **Blocker 3.1:** Third-party LLM rate limits and intermittent timeouts during large repository evaluations.  
  *Resolution:* Added exponential backoff retry logic, cached schema definitions, and encapsulated model calls inside `run_with_fallback()` wrappers.
- **Blocker 3.2:** Unstable type definitions between FastAPI backend responses and Vite frontend models.  
  *Resolution:* Implemented `api-contract-sync` skill to guarantee synchronization across `API_CONTRACT.md`, `backend/app/schemas/api_contracts.py`, and `frontend/src/types/api.ts`.

### Next Steps
- Implement full OpenTelemetry observability stack (Prometheus, Loki, Tempo, Grafana).
- Implement the autonomous On-Call Agent and VPS production deployment.

---

## Phase 4: Observability, On-Call Agent & VPS Production Deployment

### Context & Implementation
Phase 4 completed the operational maturity requirements of the project: end-to-end telemetry instrumentation, symptom-based user-impact alerting, an autonomous on-call diagnostic agent, and production deployment on a cloud VPS.

### Completed Work
- Instrumented backend and worker services with OpenTelemetry (`backend/app/core/telemetry.py`), correlating metrics, logs, and traces using a unified `trace_id`.
- Configured the LGTM observability stack in Docker Compose:
  - **Prometheus:** Scrapes `/metrics` from FastAPI; monitors request rates, error rates, and analysis job durations.
  - **Loki:** Ingests non-blocking structured logs tagged with `{app="backend"}` and `{app="worker"}`.
  - **Tempo:** Collects distributed OTLP traces (`BatchSpanProcessor`) via endpoint `http://tempo:4317`.
  - **Grafana:** Pre-provisioned dashboards (`infra/grafana/provisioning/`) displaying user-impact symptoms with trace-to-log drill-downs.
- Defined user-impacting symptom alerts in `infra/prometheus/alert_rules.yml`:
  - `HighHttpErrorRate` (HTTP 5xx responses > 5% over 5m)
  - `HighLatencyP95` (P95 response latency > 2.0s over 5m)
  - `AnalysisJobFailures` (Failed background analysis runs > 0 over 10m)
  - `ServiceDowntime` (Backend or worker instance down > 1m)
- Implemented `OnCallAgent` (`backend/app/agents/oncall_agent.py`):
  - Read-only agent bounded by `read_only_verified=True`.
  - Queries Prometheus metric rates, Loki log excerpts, Tempo traces, and incident runbooks (`infra/RUNBOOK_GEMINI_VPS.md`).
  - Synthesizes root-cause hypotheses, severity assessments, affected components, and immediate remediation steps.
- Deployed live production environment at `https://ct-academia.pl`:
  - Provisioned Ubuntu VPS with Docker Compose production stack (`docker-compose.prod.yml`).
  - Configured Nginx reverse proxy with TLS termination, HTTP/2, security headers, rate limiting, and dual health check probes:
    - Edge probe: `https://ct-academia.pl/healthz` (200 OK from Nginx)
    - Backend probe: `https://ct-academia.pl/api/v1/health` (FastAPI JSON health check)
  - Configured automated TLS certificate renewal with Certbot webroot validation.
- Engineered 3-tier GitHub Actions CI/CD workflows (`.github/workflows/ci-cd.yml`):
  - Tier 1: Pull Request CI tests (Pytest backend suite, frontend typecheck, Docker Compose validation).
  - Tier 2: Automated deployment to development/staging environment on push to `main`.
  - Tier 3: Manual approval gate for production promotion.
- Pre-seeded reviewer credentials (`reviewer@datatalks.club` / `devtrack-zoomcamp-2026`) enabling instant verification without manual registration.

### Decisions
- **Decision 4.1 (Symptom-Based Alerting):** Alert exclusively on user-impacting symptoms (5xx errors, latency spikes, job failures, downtime) rather than raw internal metrics (CPU/disk utilization), eliminating alert fatigue.
- **Decision 4.2 (Bounded Read-Only Diagnostic Agent):** `OnCallAgent` is strictly read-only. It inspects metrics, logs, traces, and runbooks to diagnose incidents, but cannot execute mutating infrastructure commands.
- **Decision 4.3 (Trace-Correlated Telemetry):** Every HTTP request injects a `trace_id` header, logs structured JSON with `trace_id`, and passes the ID to background worker jobs for complete distributed observability.
- **Decision 4.4 (VPS Memory Optimization):** Implemented strict container memory limits and swap configurations in `docker-compose.prod.yml` to ensure stable operation within a 4 GB RAM VPS footprint.

### Blockers
- **Blocker 4.1:** Memory pressure on the 4 GB VPS during simultaneous container image builds and background analysis runs.  
  *Resolution:* Applied memory limits (`mem_limit: 768m`) on backend and worker services, tuned PostgreSQL buffer pools, and optimized Docker multi-stage builds.
- **Blocker 4.2:** Bootstrapping HTTPS certificates on first deployment before Nginx is running.  
  *Resolution:* Implemented a two-stage certificate workflow in deployment scripts: generate a temporary bootstrap certificate for initial Nginx start, followed by Certbot webroot issuance and live reload.
- **Blocker 4.3:** Unguarded optional dependencies in host test environments causing test failures when testing without full backend venv.  
  *Resolution:* Added `pytest.importorskip("httpx")` and `pytest.importorskip("pydantic")` guards across test suites, ensuring clean test execution in all environments.

### Next Steps
- Final integration and continuous self-evaluation of DevTrack AI against its own repository (`https://github.com/DemidenkoD/dev_track_ai`).
- Post-course enhancements: support for private GitHub repositories via GitHub App installations and webhook-driven continuous analysis.

---

## Phase 5: Final Sync — Wave-2 Verification & Self-Analysis Gate (2026-10-26)

### Context
Wave-2 commit `0fc2aea` (ephemeral one-time email notifications + mail preflight + demo docs) synced to `origin/main`. Final Wave F1/F2/F3 verification executed against self-tracked project `81fcca26-4956-4b6d-9ccb-eb4d774f5786`.

### Verification Results (F1/F2/F3)
- **F1 — Full verification suite:** `59 passed` backend pytest, frontend `typecheck` clean (0 errors), `docker compose config` + `config-prod` valid.
- **F2 — Commit & push:** `0fc2aea` pushed to `origin/main`, HEAD in sync with `origin/main`.
- **F3 — Rebuild & analysis:** local stack rebuilt (`make up`), analysis run `a57dea1d` completed — `24 estimated / 0 verified / 83.33% dev completion`, all 9 tabs (Scorecard, Milestones, Mentor, Evidence, Diary, Security, Deployment, On-Call, Settings) return 200.

### Completed Work
- README observability/telemetry section + live deployment links synced.
- TODO Final Wave boxes ticked with SHA/run IDs (`0fc2aea`, `a57dea1d`).
- Diary Phase 5 entry appended for audit trail.

### Remaining Human Items
- **Verified triage:** review `estimated` criteria and flip to `verified` / `needs_review` with `human_override_points` where evidence warrants.
- **Scanners:** confirm Semgrep/Gitleaks/pip-audit/npm-audit/Bandit findings reviewed on self-analysis.
- **SMTP:** configure one-time notification sender for completion emails (memory-only, never persisted).
