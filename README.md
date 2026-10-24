# DevTrack AI — Course-First AI Project Mentor

> **Tagline:** Your AI mentor from project idea to deployment.

**DevTrack AI** is an advisory, read-only AI project mentor designed for **DataTalksClub Zoomcamp** participants and developers building technical course projects. It continuously evaluates a public GitHub repository, development diary, security posture, and live deployment against a versioned course rubric to answer five questions:

1. **Am I meeting the course requirements?**
2. **How many points could my project currently receive?** *(Explicitly separating Estimated, Verified, and Needs Review states—never masquerading as an official grade)*
3. **What is preventing me from receiving more points?**
4. **What should I work on next?**
5. **Is my application secure and successfully deployed?**

---

## Predefined Reviewer Credentials

Per Product Specification §3, DevTrack AI uses a single predefined account (no public registration). Reviewers can log in using:

- **Username:** `reviewer@datatalks.club` *(or overridden via `ADMIN_USERNAME` in `.env`)*
- **Password:** `devtrack-zoomcamp-2026` *(or overridden via `ADMIN_PASSWORD` in `.env`)*

---

## Repository & Multi-Agent Architecture

> **Spec:** [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md) v0.3
> **Tracker (public):** https://github.com/users/DemidenkoD/projects/4/views/1 — tasks with acceptance criteria + `Closes #n` evidence.

This repository is structured for **simultaneous multi-agent development** across 6 non-overlapping ownership tracks:

- **Problem Statement:** [docs/PROBLEM_DESCRIPTION.md](docs/PROBLEM_DESCRIPTION.md)
- **Product Specification v0.3:** [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md)
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

