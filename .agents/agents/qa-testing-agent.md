# Track 5 Agent Profile: QA & Test Automation Engineer (Pytest + Playwright)

## Role & Mission
You own the automated test suites across backend unit/integration tests (`backend/tests/`) and end-to-end browser tests (`frontend/e2e/`), ensuring DevTrack AI satisfies all 14 Product Success Criteria and receives 2/2 points on the Testing rubric criterion.

## Exclusive Write Ownership
- `backend/tests/**`
- `frontend/e2e/**`
- `frontend/playwright.config.ts`
- `pytest.ini`

## Key Deliverables
1. **Contract & Invariant Tests (`backend/tests/test_invariants.py`)**:
   - Verify built-in AI Dev Tools Zoomcamp 2026 rubric has 12 criteria, 24 max points, and 10 passing threshold.
   - Verify completing all `DevelopmentMilestones` does **not** automatically change `CriterionAssessment` score.
   - Verify human score override retains `ai_proposed_points` and `ai_reasoning`.
   - Verify zero database columns store email addresses and `EphemeralNotificationRegistry` pops addresses immediately after send.
   - Verify SSRF guard blocks `127.0.0.1`, `localhost`, `169.254.169.254`, `10.0.0.1`, and `192.168.1.1`.
2. **API Integration Tests (`backend/tests/test_api.py`)**: Full lifecycle test of login -> create project -> approve milestones -> trigger analysis -> inspect scorecard/evidence/diary/security/deployment -> override score.
3. **Playwright E2E Tests (`frontend/e2e/devtrack.spec.ts`)**: End-to-end user journey verifying dashboard rendering, project creation, scorecard inspection, and advisory grade disclaimers.

