# Parallel Development Workstreams & Phase Execution Plan

This document defines how the 4 product phases in `docs/PRODUCT_SPEC.md` map onto the 6 simultaneous agent tracks defined in `docs/specs/AGENT_TEAM_SPEC.md`.

---

## 1. Phase-by-Track Execution Matrix

| Phase | Track 1: Backend Core & API | Track 2: AI & Rubric Engine | Track 3: Worker, GitHub, Security & Deploy | Track 4: Frontend React + TS | Track 5: QA & Testing | Track 6: DevOps & Observability |
|---|---|---|---|---|---|---|
| **Phase 1: Foundation** | Auth (`POST /auth/login`), SQLAlchemy models (`projects`, `rubrics`, `milestones`, `evidence_items`), CRUD endpoints, Dashboard endpoint | Built-in Zoomcamp 2026 rubric loader, `RubricAnalyst` ingestion & initial milestone generator | Public GitHub repo validator & metadata fetcher (`github_service.py`) | Login view, Dashboard page, Project Creation wizard, Rubric Scorecard & Milestone approval UI | Auth, Project & Rubric unit/API tests (`backend/tests/test_phase1.py`) | Local `docker-compose.yml` (Postgres, Backend, Worker, Frontend, Nginx) |
| **Phase 2: Project Intelligence** | Analysis runs endpoints, Scorecard override endpoint (`PATCH /scorecard/{id}`), Evidence & Diary endpoints | `ProgressAnalyst`, `DiaryAnalyst`, `ProjectMentor` orchestrator with structured Gemini outputs | PostgreSQL job worker loop (`worker/runner.py`), shallow Git history/diff inspector, Diary file auto-discovery, daily cron scheduler | AI Project Mentor panel, Evidence Explorer, Diary Analyst view, Historical Commit SHA selector, Score Override modal | Worker pipeline tests, Mocked Gemini agent schema tests, Playwright core user journey | Worker container health checks & resource limits (`cpus`, `mem_limit`) |
| **Phase 3: Security & Deployment** | Security & Deployment endpoints, ephemeral notification wiring | `SecurityReviewer` agent (explains Semgrep/Gitleaks/pip-audit findings) | Isolated scanner runner (`semgrep`, `gitleaks`, `pip-audit`, `npm audit`, `bandit`), SSRF-safe `httpx` Deployment Monitor, in-memory one-time SMTP notifier | Security Reviewer dashboard, Deployment Monitor uptime chart, One-time email notification modal with privacy disclosure | SSRF unit tests, Scanner parser tests, Ephemeral email zero-persistence verification test | Scanner binary installation in worker Dockerfile & sandbox isolation |
| **Phase 4: Operations & Agent Capabilities** | `/api/v1/oncall/diagnose` endpoint & OpenTelemetry FastAPI middleware hooks | Bounded read-only `OnCallAgent` querying Prometheus/Loki/Tempo | Telemetry enrichment on worker jobs & scanner runs | On-Call Agent diagnostic console in UI | E2E Playwright full-stack suite + independent agent evaluation benchmark | GitHub Actions CI/CD (`.github/workflows/ci-cd.yml`), Prometheus, Loki, Tempo, Grafana dashboards & user-impact alert rules |

---

## 2. How to Launch Simultaneous Subagents

When orchestrating parallel development in Antigravity, launch subagents with scoped prompts referencing their track profile in `.agents/agents/` and their exclusive file ownership boundaries:

1. **Step 0 (Completed in Foundation Setup):** Lock shared schemas in `backend/app/schemas/api_contracts.py` and `docs/specs/`.
2. **Wave 1 (Simultaneous Execution):**
   - **Subagent A (`backend-core-agent`)**: Implement database session, models, auth, and FastAPI routers in `backend/app/{core,db,models,api}/`.
   - **Subagent B (`ai-agents-specialist`)**: Implement Gemini structured-output agents and rubric service in `backend/app/agents/` and `backend/app/services/rubric_service.py`.
   - **Subagent C (`integrations-worker-agent`)**: Implement GitHub inspector, diary parser, deterministic security scanners, SSRF-safe deployment monitor, ephemeral email notifier, and PostgreSQL worker in `backend/app/services/` and `backend/app/worker/`.
   - **Subagent D (`frontend-ui-agent`)**: Scaffold and build the React + TypeScript UI in `frontend/` against `docs/specs/API_CONTRACT.md`.
   - **Subagent E (`devops-observability-agent`)**: Build `docker-compose.yml`, Dockerfiles, Nginx config, OpenTelemetry collector/LGTM stack in `infra/`, and `.github/workflows/`.
3. **Wave 2 (Integration & Verification):**
   - **Subagent F (`qa-testing-agent`)**: Execute and expand unit, integration, security/privacy, and Playwright E2E tests in `backend/tests/` and `frontend/e2e/`.

