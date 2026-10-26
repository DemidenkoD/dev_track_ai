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
- **Backend Health Probe:** https://ct-academia.pl/api/v1/health
- **Edge Health Probe:** https://ct-academia.pl/healthz
- **OpenAPI Specification Docs:** https://ct-academia.pl/docs
- **Predefined Reviewer Credentials:**
  - **Username:** `reviewer@datatalks.club` *(or configured via `ADMIN_USERNAME` in `.env`)*
  - **Password:** `devtrack-zoomcamp-2026` *(or configured via `ADMIN_PASSWORD` in `.env`)*
  - **Role:** `reviewer` (pre-seeded account per Product Spec §3, no public registration needed)

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
pytest && npm --prefix frontend run typecheck && (cd frontend && npx playwright test)
```

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

