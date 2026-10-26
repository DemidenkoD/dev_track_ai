# DevTrack AI — Parallel Multi-Agent Finalization TODO (`TODO.md`)

> **Target:** Full 24/24 readiness against the [DataTalksClub AI Dev Tools Zoomcamp 2026 Rubric](docs/rubrics/ai_dev_tools_zoomcamp_2026.json) + complete self-evaluation on `http://localhost:5173/projects/81fcca26-4956-4b6d-9ccb-eb4d774f5786` and live production `https://ct-academia.pl`.
> **Coordination Rule:** Every task below is partitioned strictly by the **6 non-overlapping file-ownership tracks** in [`AGENTS.md`](AGENTS.md) and [`docs/specs/AGENT_TEAM_SPEC.md`](docs/specs/AGENT_TEAM_SPEC.md). All 6 tracks can run **simultaneously in parallel** without file or merge conflicts.

---

## Quick Status Overview

- [x] **Track 1 (`backend-core-agent`)** — OTLP Tempo Trace Exporter + Non-Blocking Loki Log Shipper + Default Development Milestones Seeding
- [x] **Track 2 (`ai-agents-specialist`)** — Read-Only Tempo Trace Querying in `OnCallAgent` + Evidence-Aware Offline Fallback in `RubricAnalyst`
- [x] **Track 3 (`integrations-worker-agent`)** — Complete Checkout Evidence Bundle + Wire `DiaryAnalyst`, `SecurityReviewer` & `ProjectMentor` in `analysis_pipeline.py`
- [x] **Track 4 (`frontend-ui-agent`)** — Polish Self-Tracked Project UX & Empty-State Guidance
- [x] **Track 5 (`qa-testing-agent`)** — Gate `record-demo.spec.ts` for CI + Add Host `pytest.importorskip` Guards + Verify E2E Suite
- [x] **Track 6 (`devops-observability-agent`)** — Create `docs/DIARY.md`, Document Live Deployment in `README.md`, Wire `.github/workflows/ci-cd.yml` Deploy Steps
- [ ] **Final Wave (Orchestrator / Sync Gate)** — Commit & Push to `origin/main`, Rebuild Containers (`make up`), Trigger Analysis on `81fcca26-4956-4b6d-9ccb-eb4d774f5786`

---

## Wave 1: Simultaneous Parallel Track Tasks (Zero File Overlap)

### Track 1: `backend-core-agent`
- **Profile:** [`.agents/agents/backend-core-agent.md`](.agents/agents/backend-core-agent.md)
- **Exclusive Write Boundary:** `backend/app/core/telemetry.py`, `backend/app/db/init_db.py`
- **Rubric Criteria Addressed:** `#5 application` (2/2), `#10 observability` (2/2)
- **Tasks:**
  - [x] **T1.1 — Wire OTLP Span Exporter to Tempo (`backend/app/core/telemetry.py`):**
    - In `_ensure_otel_tracer()`, read `OTEL_EXPORTER_OTLP_ENDPOINT` from `os.environ` (default `http://tempo:4317`).
    - Attach `BatchSpanProcessor(OTLPSpanExporter(endpoint=..., insecure=True))` inside a defensive `try/except Exception` block so spans flow to Tempo when running in Docker, while offline unit tests never block or fail if Tempo is unreachable.
  - [x] **T1.2 — Add Non-Blocking Loki HTTP Log Shipper (`backend/app/core/telemetry.py`):**
    - Add a best-effort, non-blocking logging handler or background emitter that ships structured log lines (`http_request ... trace_id=...` and `worker_run_finished ... trace_id=...`) to `LOKI_PUSH_URL` (default `http://loki:3100/loki/api/v1/push`) with labels `{app="backend"}` / `{app="worker"}`.
    - Enforce the privacy invariant (`AGENTS.md` §1.4): scrub any email address, Bearer token, or API key before shipping.
  - [x] **T1.3 — Seed Default Development Milestones for Example Project (`backend/app/db/init_db.py`):**
    - In `seed_example_project(db)` (and as an idempotent backfill if the example project `https://github.com/DemidenkoD/dev_track_ai` currently has `0` rows in `development_milestones`), approve the initial `AssessmentMilestone` rows (`is_approved=True`, `project.milestones_approved=True`) and seed 12 realistic `DevelopmentMilestone` tasks (one per criterion, e.g. 9 `completed`, 2 `partial`, 1 `outstanding`) so `Development Progress (tasks)` on `81fcca26-4956-4b6d-9ccb-eb4d774f5786` shows meaningful progress immediately.
    - **Invariant check:** Seeding or completing `DevelopmentMilestone` rows MUST NEVER set or alter `CriterionAssessment.ai_proposed_points` or `human_override_points`.
- **Verification Command:**
  ```bash
  pytest backend/tests/test_health_auth.py backend/tests/test_api.py -q
  ```

---

### Track 2: `ai-agents-specialist`
- **Profile:** [`.agents/agents/ai-agents-specialist.md`](.agents/agents/ai-agents-specialist.md)
- **Exclusive Write Boundary:** `backend/app/agents/oncall_agent.py`, `backend/app/agents/rubric_analyst.py`
- **Rubric Criteria Addressed:** `#11 alerting_on_user_impact` (1/1), `#12 on_call_agent` (2/2), `#1–#12` scorecard accuracy
- **Tasks:**
  - [x] **T2.1 — Add Read-Only Tempo Trace Querying to `OnCallAgent` (`backend/app/agents/oncall_agent.py`):**
    - In `OnCallAgent._fetch_readonly_telemetry(self, alert_name, time_window_minutes)`, add a read-only `client.get(f"{self.tempo_url}/api/search", params={"limit": 5})` call inside a `try/except Exception` block.
    - When status is `200`, append `{"query": "tempo:/api/search?limit=5", "excerpt": resp.text[:400]}` to `traces` so all three observability pillars (Prometheus metrics + Loki logs + Tempo traces) are queried and passed to `diagnose_incident()`.
    - Preserve `read_only_verified=True` across all code paths.
  - [x] **T2.2 — Improve Evidence-Backed Offline Fallback Scoring (`backend/app/agents/rubric_analyst.py`):**
    - In `_fallback_scored_criterion(criterion, evidence_text, evidence_paths)`, inspect both `evidence_text` and `evidence_paths` so that when rich multi-file repository evidence is present in the bundle (e.g., `docs/PROBLEM_DESCRIPTION.md` + `README.md`, `docs/PRODUCT_SPEC.md`, `docs/specs/AGENT_TEAM_SPEC.md` + `.agents/agents/`, `AGENTS.md` + `.agents/skills/`, `docker-compose.yml` + `Dockerfile`, `pytest.ini` + `backend/tests/` + `frontend/e2e/`, `.github/workflows/ci-cd.yml`, `infra/prometheus/alert_rules.yml`, `backend/app/agents/oncall_agent.py`), the fallback proposes realistic `ai_proposed_points` (up to `max_points` when all required evidence types for that criterion are present) with `score_state=ScoreState.ESTIMATED` (or `NEEDS_REVIEW` with `ai_confidence < 0.70` for live-verification criteria per `_apply_evidence_grounding`).
    - Keep all grounding guards in `_apply_evidence_grounding` intact so empty-evidence tests (`test_contract_invariants.py`, `test_invariants.py`) continue to pass 100%.
- **Verification Command:**
  ```bash
  pytest backend/tests -q -k "rubric or oncall or invariant"
  ```

---

### Track 3: `integrations-worker-agent`
- **Profile:** [`.agents/agents/integrations-worker-agent.md`](.agents/agents/integrations-worker-agent.md)
- **Exclusive Write Boundary:** `backend/app/services/analysis_pipeline.py`, `backend/app/worker/runner.py`
- **Rubric Criteria Addressed:** `#1 problem_description`, `#4 context_management`, `#5 application`, `#7 containerization`
- **Tasks:**
  - [x] **T3.1 — Expand Checkout Evidence Indexing (`backend/app/services/analysis_pipeline.py`):**
    - In `_inspect_checkout()`:
      1. Add `"docs/PROBLEM_DESCRIPTION.md"` to the `documentation` evidence tuple alongside `"docs/PRODUCT_SPEC.md"` and `"README.md"`.
      2. Add `"frontend/AGENTS.md"` and `"infra/AGENTS.md"` to the `agent_config` evidence tuple alongside `"AGENTS.md"`, `"backend/AGENTS.md"`, `"backend/app/agents/AGENTS.md"`, and `"docs/specs/AGENT_TEAM_SPEC.md"`.
      3. Add `"infra/nginx/nginx.conf"` as `docker_compose` evidence so the reverse proxy is explicitly cited for `containerization`.
  - [x] **T3.2 — Wire `DiaryAnalyst`, `SecurityReviewer` & `ProjectMentor` into Snapshot Persistence (`backend/app/services/analysis_pipeline.py`):**
    - In `_persist_diary_snapshot()`: call `app.agents.diary_analyst.analyze_diary(diary_text=result.diary_excerpt, git_commit_summaries=[f"HEAD {result.commit_sha}"], discovered_path=result.diary_path)` (inside a `try/except` falling back to current behavior) to populate `completed_work`, `blockers`, `decisions`, `next_steps`, `git_alignment_summary`, and `discrepancies`.
    - In `_persist_security_report()`: call `app.agents.security_reviewer.review_security_findings(...)` (inside a `try/except` fallback) to populate `ai_executive_summary` and per-finding `ai_explanation` / `ai_remediation`.
    - In `_persist_recommendations()`: call `app.agents.project_mentor.evaluate_project_mentor(...)` (or enrich the gap-based recommendations with `estimated_effort_hours` and `rationale`) so the **Mentor** tab displays rich, actionable tasks.
- **Verification Command:**
  ```bash
  pytest backend/tests/test_invariants.py -q
  ```

---

### Track 4: `frontend-ui-agent`
- **Profile:** [`.agents/agents/frontend-ui-agent.md`](.agents/agents/frontend-ui-agent.md)
- **Exclusive Write Boundary:** `frontend/src/components/InfoPanels.tsx`, `frontend/src/pages/ProjectDetailPage.tsx`
- **Rubric Criteria Addressed:** `#5 application` (2/2)
- **Tasks:**
  - [x] **T4.1 — Improve Empty-State & Self-Tracked Run UX (`frontend/src/components/InfoPanels.tsx`, `frontend/src/pages/ProjectDetailPage.tsx`):**
    - When an analysis run is in `queued` or `running` status in `ProjectDetailPage.tsx`, auto-poll `listAnalyses` / `load()` every 4 seconds until the run transitions to `completed` or `failed`, so clicking **Run analysis** updates the Scorecard, Diary, Security, and Mentor tabs automatically without requiring manual browser refreshes.
    - Ensure `DiaryPanel` in `InfoPanels.tsx` renders `decisions`, `blockers`, `next_steps`, and `discrepancies` clearly when populated by `DiaryAnalyst`.
- **Verification Command:**
  ```bash
  npm --prefix frontend run typecheck && npm --prefix frontend run build
  ```

---

### Track 5: `qa-testing-agent`
- **Profile:** [`.agents/agents/qa-testing-agent.md`](.agents/agents/qa-testing-agent.md)
- **Exclusive Write Boundary:** `frontend/e2e/record-demo.spec.ts`, `backend/tests/test_invariants.py`, `backend/tests/test_oncall.py`
- **Rubric Criteria Addressed:** `#6 testing` (2/2)
- **Tasks:**
  - [x] **T5.1 — Gate Demo Video Recorder Spec in CI (`frontend/e2e/record-demo.spec.ts`):**
    - Add `test.skip(!process.env.RECORD_DEMO, 'Guided demo video recording only runs when RECORD_DEMO=1');` at the start of the test in `frontend/e2e/record-demo.spec.ts`, and change fallback `baseURL` from `http://localhost:5174` to `http://localhost:5173`. This prevents `npx playwright test` in `.github/workflows/ci-cd.yml` from failing or timing out during CI runs.
  - [x] **T5.2 — Add Missing `pytest.importorskip` Guards for Host Test Runs (`backend/tests/test_invariants.py`, `backend/tests/test_oncall.py`):**
    - In `TestSSRFBlockingLive.test_evil_redirect_target_blocked` and `test_more_than_three_hops_is_too_many_redirects` (`backend/tests/test_invariants.py`), replace bare `import httpx` with `httpx = pytest.importorskip("httpx")`.
    - In `TestOnCallAgentDiagnosis.test_oncall_agent_class_resolves_via_protocol` (`backend/tests/test_oncall.py`), add `pytest.importorskip("pydantic")` before importing `app.agents.oncall_agent`.
- **Verification Command:**
  ```bash
  pytest backend/tests -q && npm --prefix frontend run typecheck
  ```

---

### Track 6: `devops-observability-agent` (+ Repo Docs)
- **Profile:** [`.agents/agents/devops-observability-agent.md`](.agents/agents/devops-observability-agent.md)
- **Exclusive Write Boundary:** `docs/DIARY.md`, `README.md`, `.github/workflows/ci-cd.yml`, `.gitignore`
- **Rubric Criteria Addressed:** `#1 problem_description` (2/2), `#8 deployment` (2/2), `#9 ci_cd` (3/3)
- **Tasks:**
  - [x] **T6.1 — Create Engineering Development Diary (`docs/DIARY.md`):**
    - Create `docs/DIARY.md` documenting the chronological engineering log across Phases 1–4 (problem formulation, dual-layer 6-track agent architecture, SQLAlchemy 2.0 + FastAPI contract lock, deterministic security scanners + SSRF guard, ephemeral notifications, OpenTelemetry LGTM stack, bounded read-only On-Call Agent, and VPS HTTPS deployment at `https://ct-academia.pl`), including completed work, architectural decisions, blockers resolved, and next steps.
  - [x] **T6.2 — Document Live Production Deployment & Problem Summary in `README.md`:**
    - Add a prominent **Live Production Deployment** section near the top of `README.md` with:
      - Live App URL: `https://ct-academia.pl`
      - Live Health Probe: `https://ct-academia.pl/api/v1/health`
      - Edge Health Probe: `https://ct-academia.pl/healthz`
      - Predefined Reviewer Credentials (`reviewer@datatalks.club` / `devtrack-zoomcamp-2026`)
    - Add a concise **Problem & Solution Summary** section directly in `README.md` (linking to `docs/PROBLEM_DESCRIPTION.md` and `docs/PRODUCT_SPEC.md`) so both `README.md` and `docs/` satisfy Criterion #1 (`problem_description` 2/2).
  - [x] **T6.3 — Wire Real Conditional SSH Deploy in `.github/workflows/ci-cd.yml`:**
    - Replace the `echo "... deploy step is a commented template ..."` lines in `deploy-development` and `promote-production` in `.github/workflows/ci-cd.yml` with clean, working conditional SSH deployment steps (using `STAGING_SSH_HOST` / `VPS_IP` and `PROD_SSH_HOST` when configured, and logging a clean `::notice::` when running in fork/PR environments without SSH secrets).
  - [x] **T6.4 — Update `.gitignore` for Local Scratch/Override Files:**
    - Ensure local-only temporary artifacts are appropriately handled so `git status` is clean for commit.
- **Verification Command:**
  ```bash
  make config && make config-prod
  ```

---

## Wave 2: Final Integration, Commit, Push & Self-Analysis Gate

Once Tracks 1–6 complete their Wave 1 tasks:

- [ ] **F1 — Run Full Verification Suite:**
  ```bash
  make test-backend && npm --prefix frontend run typecheck && make config && make config-prod
  ```
- [ ] **F2 — Commit & Push All Changes to `origin/main`:**
  - Stage updated specs (`docs/PRODUCT_SPEC.md`, `docs/DIARY.md`, `TODO.md`), backend, frontend, tests, and workflows, then commit and push to `origin/main` so the public GitHub repository `https://github.com/DemidenkoD/dev_track_ai` has all latest files on `main`.
- [ ] **F3 — Rebuild Local Stack & Trigger Analysis on `81fcca26-4956-4b6d-9ccb-eb4d774f5786`:**
  - Run `make up` to rebuild `backend`, `worker`, and `frontend`.
  - Trigger a new analysis on `http://localhost:5173/projects/81fcca26-4956-4b6d-9ccb-eb4d774f5786` and verify all 9 tabs (**Scorecard**, **Milestones**, **Mentor**, **Evidence**, **Diary**, **Security**, **Deployment**, **On-Call**, **Settings**) are populated.

