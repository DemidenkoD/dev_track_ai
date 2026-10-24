# Frontend Agent Rules (`frontend/AGENTS.md`)

These rules apply to all agents working inside `frontend/`.

## 1. Tech Stack & Conventions
- **Framework:** React 18+ with TypeScript and Vite.
- **Styling:** Clean, modern dark/light developer dashboard styling (Tailwind CSS or modular CSS variables) with accessible contrast, clear status badges, and responsive layout.
- **API Client:** Centralize all HTTP calls in `frontend/src/api/client.ts` targeting `/api/v1`. Types in `frontend/src/types/api.ts` must mirror `docs/specs/API_CONTRACT.md` and `backend/app/schemas/api_contracts.py`.

## 2. Required Product UI Modules & Guardrails
1. **Project Dashboard:** Multi-project cards showing **Development Progress (%)** and **Expected Course Score (X / 24)** as two distinct metrics, plus upcoming deadlines, security badge, and deployment badge.
2. **Explicit Advisory Disclaimer:** The Rubric Scorecard and Dashboard must clearly display that AI-estimated points are **advisory estimates**, never an official course grade, and visually distinguish `Estimated`, `Verified`, and `Needs Review` states.
3. **Human Override Side-by-Side View:** When a criterion score is overridden by a human reviewer, display both the **Human Override Score + Reason** and the **Original AI Proposed Score + Reasoning**.
4. **Two-Level Milestone View:** Separate **Assessment Milestones** (official course criteria + approval banner) from **Development Milestones** (actionable engineering tasks).
5. **One-Time Email Notification Disclosure:** In the manual analysis trigger modal, include an explicit checkbox/disclosure stating: *"Your email address is held in volatile memory for this single run only, never stored in the database or logs, and may be lost if the server restarts."*

