# DevTrack AI — Course-First AI Project Mentor

> **Tagline:** Your AI mentor from project idea to deployment.

**DevTrack AI** is an advisory, read-only AI project mentor designed for **DataTalksClub Zoomcamp** participants and developers building technical course projects. It continuously evaluates a public GitHub repository, development diary, security posture, and live deployment against a versioned course rubric to answer five questions:

1. **Am I meeting the course requirements?**
2. **How many points could my project currently receive?** *(Explicitly separating Estimated, Verified, and Needs Review states—never masquerading as an official grade)*
3. **What is preventing me from receiving more points?**
4. **What should I work on next?**
5. **Is my application secure and successfully deployed?**

---

## Live Production Deployment

DevTrack AI is deployed live on a public cloud VPS with full HTTPS, edge TLS termination, automated Certbot renewal, and OpenTelemetry instrumentation:

- **Live Application URL:** https://ct-academia.pl
- **Live On-Call Incident Triage UI:** https://ct-academia.pl/oncall
- **Backend Health & Telemetry Probe:** https://ct-academia.pl/api/v1/health
- **Edge Health Probe:** https://ct-academia.pl/healthz
- **OpenAPI Specification Docs:** https://ct-academia.pl/docs
- **Predefined Reviewer Credentials:**
  - **Username:** `reviewer@datatalks.club` *(or configured via `ADMIN_USERNAME` in `.env`)*
  - **Password:** `devtrack-zoomcamp-2026` *(or configured via `ADMIN_PASSWORD` in `.env`)*
  - **Role:** `reviewer` (pre-seeded account per Product Spec §3, no public registration needed)

---

## Official Rubric Self-Assessment Matrix (24 / 24 Points)

> **Source Rubric:** [DataTalksClub AI Dev Tools Zoomcamp 2026 Project Rubric](https://github.com/DataTalksClub/ai-dev-tools-zoomcamp/tree/main/project) ([`docs/rubrics/ai_dev_tools_zoomcamp_2026.json`](docs/rubrics/ai_dev_tools_zoomcamp_2026.json)).  
> **Passing Threshold:** 10 / 24 points. **DevTrack AI Self-Assessment: 24 / 24 points (100%).**

| # | Rubric Criterion | Max | Claimed | Evidence & Implementation Files | Verification Method / Command |
| :-: | :--- | :-: | :-: | :--- | :--- |
| **1** | **Problem Description** | 2 | **2** | [docs/PROBLEM_DESCRIPTION.md](docs/PROBLEM_DESCRIPTION.md) & [§Problem Summary](#problem--solution-summary) | Comprehensive problem context, target personas, and 5 student failure modes |
| **2** | **Product Specification** | 2 | **2** | [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md), [API Contract](docs/specs/API_CONTRACT.md), [DB Schema](docs/specs/DATABASE_SCHEMA.md) | Features F1–F8, architecture, data model, security, and acceptance criteria AC1–AC6 |
| **3** | **Agent Team Specification** | 2 | **2** | [docs/specs/AGENT_TEAM_SPEC.md](docs/specs/AGENT_TEAM_SPEC.md), [.agents/agents/](.agents/agents/) | 6 non-overlapping development tracks + 6 runtime agent schemas |
| **4** | **Context Management** | 2 | **2** | Hierarchical [AGENTS.md](AGENTS.md) files + 5 modular [.agents/skills/](.agents/skills/) | Progressive disclosure: root, backend, frontend, infra `AGENTS.md` + reusable skills |
| **5** | **Application** | 2 | **2** | [docker-compose.yml](docker-compose.yml), [backend/](backend/), [frontend/](frontend/) | `make up` boots full-stack app end-to-end locally with single command |
| **6** | **Testing** | 2 | **2** | [backend/tests/](backend/tests/), [frontend/e2e/](frontend/e2e/), [Makefile](Makefile) | **`make test`** runs backend pytest + frontend typecheck in a single command |
| **7** | **Containerization** | 2 | **2** | [docker-compose.yml](docker-compose.yml), [docker-compose.prod.yml](docker-compose.prod.yml), `*/Dockerfile` | `make config && make config-prod` validates all orchestrated containers |
| **8** | **Deployment** | 2 | **2** | Live VPS deployment with HTTPS, edge TLS, and reviewer access | [https://ct-academia.pl](https://ct-academia.pl) (health: `/healthz`, `/api/v1/health`) |
| **9** | **CI/CD** | 3 | **3** | [.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml) | **3pts:** PR CI tests + auto-deploy dev + **manual production approval gate** |
| **10** | **Observability** | 2 | **2** | Prometheus, Loki, Tempo, Grafana pre-provisioned dashboard | Correlated via `trace_id`; see [Telemetry Stack Architecture](#observability-telemetry--on-call-agent-rubric-10-11-12) |
| **11** | **User-Impact Alerting** | 1 | **1** | [infra/prometheus/alert_rules.yml](infra/prometheus/alert_rules.yml) | 4 SLO alerts on user impact (5xx rate, p95 latency, worker queue, downtime) |
| **12** | **On-Call Agent** | 2 | **2** | [backend/app/agents/oncall_agent.py](backend/app/agents/oncall_agent.py), [frontend UI](/oncall) | Bounded read-only incident diagnosis querying Prometheus/Loki/Tempo + runbooks |
| | **Total Score** | **24** | **24** | | **All 12 criteria comprehensively fulfilled** |

---

## Video Walkthrough & Interactive Demo

> **Full Walkthrough (~2m 45s):** End-to-end guided product tour generated via Playwright Chromium automation and ElevenLabs voiceover narration.

- **Direct Video File:** [demo/devtrack_ai_demo.webm](demo/devtrack_ai_demo.webm)
- **Interactive Teleprompter & Audio Studio:** [demo/index.html](demo/index.html)
- **Subtitles (WebVTT):** [demo/audio/demo_subtitles.vtt](demo/audio/demo_subtitles.vtt)

<video src="demo/devtrack_ai_demo.webm" controls="controls" width="100%" style="max-width: 800px;">
  Your browser does not support the video tag. You can view or download the walkthrough directly: <a href="demo/devtrack_ai_demo.webm">demo/devtrack_ai_demo.webm</a>.
</video>

### Walkthrough Scenes Overview

| Scene | Duration | Topic | Key Rubric Capability Demonstrated |
| :--- | :---: | :--- | :--- |
| **1. Intro & Problem** | ~25s | Course dropout dilemma & blindspots | Problem description & course-first motivation |
| **2. Login & Dashboard** | ~19s | Pre-seeded reviewer login & assignments | Two-dimensional tracking: Development Progress vs Expected Score |
| **3. Rubric Scorecard** | ~28s | 12-criterion Zoomcamp scorecard | Score states (`estimated` / `verified` / `needs_review`) & human override protection |
| **4. Analysis Pipeline** | ~22s | Read-only repo inspection & security scans | Sandboxed Semgrep, Gitleaks, Bandit, SSRF-safe probers |
| **5. AI Mentor Chat** | ~24s | Evidence-backed remediation recommendations | Rubric-gap targeting & split milestone management |
| **6. Phase 4 Observability** | ~19s | Prometheus, Grafana, Loki, Tempo & On-Call | Trace correlation (`trace_id`) & bounded read-only `OnCallAgent` |
| **7. Architecture & Closing** | ~18s | 6-track parallel team structure & `make up` | Single-command startup & complete project verification |

*To re-record or customize the walkthrough locally, run [`bash scripts/record_demo.sh`](scripts/record_demo.sh).*

---

## Problem & Solution Summary

### The Problem
Technical course students frequently drop out or receive reduced scores due to five recurring failure modes:
1. **Requirements Blindspots:** Missing critical rubric items (e.g., containerization or observability) despite functional code.
2. **Silent Degradation:** Broken builds, unpinned dependencies, or expired endpoints going unnoticed until final grading.
3. **Premature Optimization & Last-Minute Rushing:** Polishing non-rubric features while missing baseline passing criteria.
4. **False Confidence:** Relying on ungrounded conversational advice without actual repository artifact verification.
5. **Unverifiable Demos:** Missing live deployment URLs, absent reviewer credentials, or unreachable health probes.

Detailed analysis of the student journey and shortfall of existing tools is documented in [docs/PROBLEM_DESCRIPTION.md](docs/PROBLEM_DESCRIPTION.md).

### The Solution
DevTrack AI provides an automated, read-only AI mentor that connects to a public GitHub repository and delivers continuous rubric-grounded guidance:
- **Evidence-Grounded Scorecard:** Evaluates 12 course criteria (24 points max, 10 passing) into explicit states: `estimated`, `verified`, or `needs_review`.
- **Dual Progress Tracking:** Separates actionable task completion (**Development Progress**) from rubric points (**Course Score**).
- **Security & Diary Alignment:** Runs deterministic security scanners (`semgrep`, `gitleaks`, `bandit`, `pip-audit`, `npm audit`) and reconciles developer diary claims against real git commit history.
- **Actionable Mentorship:** Generates prioritized, effort-estimated remediation steps targeting score gaps.
- **Operational Reliability:** Monitors live deployment health with SSRF-protected probers and provides an autonomous, read-only `OnCallAgent` to diagnose production incidents.

A comprehensive chronological engineering log detailing architectural decisions, blockers, and solutions across Phases 1–4 is documented in [docs/DIARY.md](docs/DIARY.md).

---

## Single-Command Startup & Testing

### 1. Start the Full Stack Locally (Single Command)

```bash
make up
# or: docker compose up --build -d
```

- **Frontend UI:** `http://localhost:5173`
- **Backend OpenAPI Docs:** `http://localhost:8000/docs`
- **Health Endpoint:** `http://localhost:8000/api/v1/health`
- **Prometheus Metrics & Alerts:** `http://localhost:9090/alerts`
- **Grafana Dashboards:** `http://localhost:3000` (pre-provisioned `DevTrack AI — User-Impact Overview` dashboard correlating Prometheus metrics, Loki logs, and Tempo traces via `trace_id`)

### 2. Run Automated Tests (Single Command)

```bash
# Run backend pytest + frontend typecheck in a single command:
make test

# Or run tests directly across subpackages:
pytest backend/tests && npm --prefix frontend run typecheck && (cd frontend && npx playwright test)
```

---

## CI/CD Pipeline Architecture (Rubric #9 — 3 / 3 Points)

The continuous integration and deployment pipeline in [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml) is structured to achieve the highest rubric tier (**3 / 3 points**):

1. **Pull Request CI (1 pt):** Every pull request automatically triggers the `ci` pipeline (`backend-checks` running pytest, `frontend-checks` running typecheck and build, plus Docker Compose linting). Unsound code cannot merge.
2. **Automated Continuous Deployment to Development (2 pts):** Merging or pushing to `main` automatically triggers `deploy-development`, building images and deploying to the development environment.
3. **Manual Production Promotion Gate (3 pts):** Production deployment to `https://ct-academia.pl` is strictly protected. The `promote-production` workflow requires an explicit manual trigger (`workflow_dispatch`) and passes through a GitHub Environment approval gate (`environment: production`) with protected secrets and branch restrictions—preventing untracked auto-deployments to production.

---

## Observability, Telemetry & On-Call Agent (Rubric #10, #11, #12)

DevTrack AI implements full four-pillar observability (**Metrics, Logs, Traces, Dashboards**) correlated by a single 32-character hexadecimal `trace_id`, paired with an autonomous, bounded read-only AI diagnostic agent.

### Telemetry Stack Architecture

- **Metrics (Prometheus):** Instruments `http_requests_total`, `http_request_duration_seconds`, `analysis_runs_completed_total`, and `analysis_runs_failed_total` scraped via `GET /metrics`.
- **Logs (Loki):** Structured logs with `trace_id=...` are shipped non-blockingly to Loki (`{app="backend"}`, `{app="worker"}`) with automated scrubbing of sensitive emails, tokens, and keys.
- **Traces (Tempo):** OpenTelemetry Python SDK exports traces over OTLP gRPC (`:4317`) to Grafana Tempo, propagating span context across API requests and analysis jobs.
- **Visual Dashboards (Grafana):** Pre-provisioned `DevTrack AI — User-Impact Overview` dashboard correlating 5xx rates, latency spikes, and worker queue lag.
- **User-Impact Alerting:** 4 SLO-driven Prometheus alert rules (`HighHttp5xxErrorRate`, `HighApiLatencyP95`, `AnalysisWorkerJobFailures`, `TargetDeploymentDown`).
- **Bounded Read-Only On-Call Agent:** `backend/app/agents/oncall_agent.py` queries Prometheus, Loki, and Tempo in real time to diagnose active incidents without mutating production state.

### Observability Links & Verification

| Capability | Local Development (`make up`) | Live Production VPS (`ct-academia.pl`) |
| :--- | :--- | :--- |
| **On-Call Triage UI** | [`http://localhost:5173/oncall`](http://localhost:5173/oncall) | **[`https://ct-academia.pl/oncall`](https://ct-academia.pl/oncall)** *(or Project Detail → On-Call tab)* |
| **On-Call Diagnose API** | `http://localhost:8000/api/v1/oncall/diagnose` | **[`https://ct-academia.pl/api/v1/oncall/diagnose`](https://ct-academia.pl/api/v1/oncall/diagnose)** |
| **Backend Health Probe** | `http://localhost:8000/api/v1/health` | **[`https://ct-academia.pl/api/v1/health`](https://ct-academia.pl/api/v1/health)** |
| **Edge Health Probe** | `http://localhost/healthz` | **[`https://ct-academia.pl/healthz`](https://ct-academia.pl/healthz)** |
| **Grafana Dashboard** | [`http://localhost:3000`](http://localhost:3000) *(admin / `devtrack-zoomcamp-2026`)* | Internal Docker network. Forward via: `ssh -L 3000:localhost:3000 <user>@ct-academia.pl` |
| **Prometheus & Alerts** | [`http://localhost:9090`](http://localhost:9090) / [`/alerts`](http://localhost:9090/alerts) | Internal Docker network. Forward via: `ssh -L 9090:localhost:9090 <user>@ct-academia.pl` |
| **Tempo Trace Receiver** | `http://localhost:3200` *(OTLP gRPC `:4317`)* | Internal Docker network (`tempo:4317`) |
| **Loki Log Ingestion** | `http://localhost:3100/ready` | Internal Docker network (`loki:3100`) |

---

## Repository & Multi-Agent Architecture

> **Spec:** [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md) v0.4
> **Tracker (public):** https://github.com/users/DemidenkoD/projects/4/views/1 — tasks with acceptance criteria + `Closes #n` evidence.

This repository is structured for **simultaneous multi-agent development** across 6 non-overlapping ownership tracks:

- **Problem Statement:** [docs/PROBLEM_DESCRIPTION.md](docs/PROBLEM_DESCRIPTION.md)
- **Engineering Diary:** [docs/DIARY.md](docs/DIARY.md)
- **Product Specification v0.4:** [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md)
- **Agent Team & Ownership Matrix:** [docs/specs/AGENT_TEAM_SPEC.md](docs/specs/AGENT_TEAM_SPEC.md)
- **Database Schema Specification:** [docs/specs/DATABASE_SCHEMA.md](docs/specs/DATABASE_SCHEMA.md)
- **OpenAPI 3.1 REST Contract:** [docs/specs/API_CONTRACT.md](docs/specs/API_CONTRACT.md)
- **Parallel Workstreams Plan:** [docs/specs/PARALLEL_WORKSTREAMS.md](docs/specs/PARALLEL_WORKSTREAMS.md)
- **Built-In Zoomcamp 2026 Rubric (12 Criteria, 24 Points):** [docs/rubrics/ai_dev_tools_zoomcamp_2026.json](docs/rubrics/ai_dev_tools_zoomcamp_2026.json)

### Context Management & Agent Customization Files

- **Hierarchical Rules (`AGENTS.md`)**:
  - Root rules: [AGENTS.md](AGENTS.md)
  - Backend rules: [backend/AGENTS.md](backend/AGENTS.md)
  - Runtime Gemini Agents rules: [backend/app/agents/AGENTS.md](backend/app/agents/AGENTS.md)
  - Frontend rules: [frontend/AGENTS.md](frontend/AGENTS.md)
  - Infrastructure & Observability rules: [infra/AGENTS.md](infra/AGENTS.md)
- **Development Agent Profiles (`.agents/agents/`)**:
  - [backend-core-agent.md](.agents/agents/backend-core-agent.md)
  - [ai-agents-specialist.md](.agents/agents/ai-agents-specialist.md)
  - [integrations-worker-agent.md](.agents/agents/integrations-worker-agent.md)
  - [frontend-ui-agent.md](.agents/agents/frontend-ui-agent.md)
  - [qa-testing-agent.md](.agents/agents/qa-testing-agent.md)
  - [devops-observability-agent.md](.agents/agents/devops-observability-agent.md)
- **Modular On-Demand Skills (`.agents/skills/`)**:
  - [api-contract-sync](.agents/skills/api-contract-sync/SKILL.md)
  - [db-migrations](.agents/skills/db-migrations/SKILL.md)
  - [rubric-evaluation](.agents/skills/rubric-evaluation/SKILL.md)
  - [security-scanners](.agents/skills/security-scanners/SKILL.md)
  - [on-call-diagnostics](.agents/skills/on-call-diagnostics/SKILL.md)

