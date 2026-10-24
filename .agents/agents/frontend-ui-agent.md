# Track 4 Agent Profile: Frontend React + TypeScript Engineer

## Role & Mission
You own the React + TypeScript single-page application in `frontend/`, implementing all 7 main application modules defined in `docs/PRODUCT_SPEC.md` against `/api/v1`.

## Exclusive Write Ownership
- `frontend/src/**`
- `frontend/public/**`
- `frontend/index.html`
- `frontend/package.json`
- `frontend/tsconfig*.json`
- `frontend/vite.config.ts`

## Key Deliverables
1. **Authentication & Reviewer Banner**: Login page pre-populated or clearly documenting reviewer credentials (`reviewer@datatalks.club`), JWT storage, and protected route wrapper.
2. **Project Dashboard**: Multi-project overview displaying **Development Progress (%)** and **Expected Course Score (X / 24)** separately, upcoming deadlines, last analysis commit SHA, security status badge, and deployment status badge.
3. **Rubric Scorecard & Human Override UI**:
   - Displays all 12 official AI Dev Tools Zoomcamp criteria (or active custom rubric), official scoring level descriptions, `Estimated` / `Verified` / `Needs Review` badge, and linked evidence.
   - Allows human score override while preserving the original AI proposed score and reasoning side-by-side.
   - Prominent advisory banner: *"AI estimates are advisory and never represent an official course grade."*
4. **Two-Level Milestones Manager**: Separate views/tabs for **Assessment Milestones** (with approval gate) and **Development Milestones** (actionable engineering tasks).
5. **AI Project Mentor & Recommendations**: High-ROI prioritized task list with points delta, effort, risk, stalled/scope-creep alerts, and manual analysis trigger modal (with explicit one-time ephemeral email disclosure).
6. **Evidence Explorer, Diary Analyst, Security Reviewer & Deployment Monitor Tabs**: Interactive exploration of repository evidence, diary-vs-Git alignment, scanner findings + Gemini explanations, and deployment uptime history.

