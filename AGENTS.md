# DevTrack AI — Root Agent Rules & Context Management (`AGENTS.md`)

Welcome to **DevTrack AI** ("Your AI mentor from project idea to deployment"). Every agent operating in this repository MUST adhere to these architectural invariants, safety constraints, and parallel file-ownership boundaries.

---

## 1. Core Product & Domain Invariants

1. **Advisory & Read-Only Only:** DevTrack AI inspects public GitHub repositories, development diaries, security findings, and live deployments. It **never** pushes commits, opens PRs, or modifies user repositories.
2. **Never Present AI Estimates as Official Grades:**
   - Every criterion assessment has an explicit `score_state`: `estimated`, `verified`, or `needs_review`.
   - When a human overrides a score (`human_override_points`), the original `ai_proposed_points` and `ai_reasoning` **must remain stored and visible** for comparison.
   - All UI views and API responses must distinguish official rubric criteria from AI-generated recommendations.
3. **Two Separate Milestone & Progress Dimensions:**
   - **Assessment Milestones:** Official course rubric criteria and point values (e.g., 12 criteria, 24 max points, 10/24 passing threshold for AI Dev Tools Zoomcamp 2026).
   - **Development Milestones:** Actionable implementation tasks linked to assessment criteria. Completing development subtasks **must never automatically award** the official assessment criterion score.
   - Progress is always tracked across two separate dimensions: **Development Completion** vs. **Expected Course Score**.
4. **Zero Persistent Email Storage (One-Time Notifications):**
   - Optional one-time email notifications must **never** be persisted in PostgreSQL, written to log files, or included in OpenTelemetry traces/metrics.
   - Hold the email address strictly in volatile process memory while the analysis job is pending and purge it immediately upon sending or failure.
5. **Security & SSRF Protection:**
   - Only public GitHub repositories (`https://github.com/<owner>/<repo>`) are permitted.
   - Never execute arbitrary code or scripts from an inspected repository. Run deterministic scanners (`semgrep`, `gitleaks`, `pip-audit`, `npm audit`, `bandit`) in isolated subprocesses with strict timeouts.
   - All deployment monitoring (`httpx`) must validate resolved IP addresses to block private/loopback/link-local/cloud-metadata IP ranges (SSRF protection).

---

## 2. Parallel Multi-Agent Ownership Boundaries

When working as part of a simultaneous multi-agent team, stay strictly within your assigned directory boundary unless explicitly instructed by the user or orchestrator:

- **Track 1 (`backend-core-agent`)**: `backend/app/core/`, `backend/app/db/`, `backend/app/models/`, `backend/app/schemas/`, `backend/app/api/`, `backend/app/main.py`
- **Track 2 (`ai-agents-specialist`)**: `backend/app/agents/`, `backend/app/services/rubric_service.py`, `docs/rubrics/`
- **Track 3 (`integrations-worker-agent`)**: `backend/app/worker/`, `backend/app/services/{github_service,diary_service,security_scanner,deployment_monitor,notification_service}.py`
- **Track 4 (`frontend-ui-agent`)**: `frontend/src/`, `frontend/index.html`, `frontend/package.json`, `frontend/vite.config.ts`
- **Track 5 (`qa-testing-agent`)**: `backend/tests/`, `frontend/e2e/`, `frontend/playwright.config.ts`
- **Track 6 (`devops-observability-agent`)**: `docker-compose*.yml`, `*/Dockerfile`, `infra/`, `.github/workflows/`, `Makefile`

Read `docs/specs/AGENT_TEAM_SPEC.md` for full coordination protocols and `docs/specs/API_CONTRACT.md` + `backend/app/schemas/api_contracts.py` for the locked API contract.

---

## 3. Environment & Credentials Protocol

- Environment variables are loaded from `.env` (template in `.env.example`).
- **Never** print, log, or commit secret values from `.env` (`GEMINI_API_KEY`, `MAIL_SMTP_PASS`, `SECRET_KEY`).
- Use `GEMINI_API_KEY` and `GEMINI_MODEL` via the official `google-genai` SDK (`from google import genai`).

---

## 4. Scoped Subdirectory Rules & Skills

- Scoped rules are located in `backend/AGENTS.md`, `backend/app/agents/AGENTS.md`, `frontend/AGENTS.md`, and `infra/AGENTS.md`.
- Reusable procedural skills are located in `.agents/skills/<skill-name>/SKILL.md`. Activate the relevant skill whenever modifying API schemas, database migrations, rubric evaluations, security scanners, or on-call diagnostics.

