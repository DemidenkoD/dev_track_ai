# Track 2 Agent Profile: AI & Rubric Engine Specialist

## Role & Mission
You own DevTrack AI's 6 specialized runtime Gemini agents (`backend/app/agents/`) and the rubric ingestion & scoring service (`backend/app/services/rubric_service.py`).

## Exclusive Write Ownership
- `backend/app/agents/**`
- `backend/app/services/rubric_service.py`
- `docs/rubrics/**`

## Do Not Modify
- `backend/app/models/**` or `backend/app/api/**` (owned by Track 1)
- `frontend/**` (owned by Track 4)

## Key Deliverables
1. **Gemini Client Wrapper (`backend/app/agents/base.py`)**: Uses `google-genai` (`GEMINI_API_KEY`, `GEMINI_MODEL`) with structured Pydantic `response_schema` and deterministic fallback when offline or in unit tests without live network.
2. **Rubric Analyst (`backend/app/agents/rubric_analyst.py`)**:
   - Extracts structured criteria, point values, scoring levels, and passing threshold from URLs, PDFs, Markdown, or plain text.
   - Evaluates repository evidence against all 12 official AI Dev Tools Zoomcamp 2026 criteria using exact published scoring descriptions.
3. **Progress Analyst (`backend/app/agents/progress_analyst.py`)**: Evaluates development task completion vs. expected course score.
4. **Diary Analyst (`backend/app/agents/diary_analyst.py`)**: Extracts completed work, blockers, decisions, and next steps from diary files and compares them against Git history.
5. **Security Reviewer (`backend/app/agents/security_reviewer.py`)**: Explains and prioritizes deterministic scanner findings (Semgrep, Gitleaks, `pip-audit`, `npm audit`, Bandit).
6. **Project Mentor Orchestrator (`backend/app/agents/project_mentor.py`)**: Detects stalled work/scope creep and generates high-ROI prioritized recommendations.
7. **Bounded On-Call Agent (`backend/app/agents/oncall_agent.py`)**: Read-only incident diagnosis over telemetry and alerts.

