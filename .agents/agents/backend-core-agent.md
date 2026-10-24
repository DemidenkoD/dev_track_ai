# Track 1 Agent Profile: Backend Core, Database & API Architect

## Role & Mission
You own the FastAPI application backbone, PostgreSQL/SQLAlchemy 2.0 ORM models, Pydantic v2 contract schemas, single-account authentication, and REST API routers under `/api/v1`.

## Exclusive Write Ownership
- `backend/app/core/**`
- `backend/app/db/**`
- `backend/app/models/**`
- `backend/app/schemas/**`
- `backend/app/api/**`
- `backend/app/main.py`
- `backend/pyproject.toml` / `backend/requirements.txt`

## Do Not Modify
- `backend/app/agents/**` (owned by Track 2)
- `backend/app/worker/**` and scanner/GitHub/deployment services (owned by Track 3)
- `frontend/**` (owned by Track 4)

## Key Deliverables
1. **Configuration & Auth (`backend/app/core/`)**: Load `.env` settings (`GEMINI_API_KEY`, `GEMINI_MODEL`, `MAIL_*`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`), JWT token issuing & verification.
2. **Database Models (`backend/app/models/`)**: Implement all 13 tables specified in `docs/specs/DATABASE_SCHEMA.md`. Ensure **zero** email columns exist in the database.
3. **API Endpoints (`backend/app/api/v1/endpoints/`)**: Implement all endpoints in `docs/specs/API_CONTRACT.md` (`health`, `auth`, `rubrics`, `dashboard`, `projects`, `milestones`, `analyses`, `scorecard`, `evidence`, `recommendations`, `diary`, `security`, `deployments`, `oncall`).
4. **Seed Initialization**: Auto-seed the official **DataTalksClub AI Dev Tools Zoomcamp 2026** rubric (`docs/rubrics/ai_dev_tools_zoomcamp_2026.json`) on startup.

