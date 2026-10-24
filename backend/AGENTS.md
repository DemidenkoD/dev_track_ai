# Backend Agent Rules (`backend/AGENTS.md`)

These rules apply to all agents working inside `backend/`.

## 1. Tech Stack & Conventions
- **Framework:** FastAPI (Python 3.12+), Pydantic v2 (`pydantic`, `pydantic-settings`), SQLAlchemy 2.0 (`Mapped`, `mapped_column`).
- **Database:** PostgreSQL (`psycopg` driver) for production/Docker; tests may use SQLite in-memory or test Postgres fixtures via FastAPI dependency overrides (`get_db`).
- **API Prefix:** All REST endpoints live under `/api/v1` and must match `docs/specs/API_CONTRACT.md` and `backend/app/schemas/api_contracts.py`.

## 2. Non-Negotiable Backend Invariants
1. **Single Predefined Account:** Authentication validates credentials against `ADMIN_USERNAME` and `ADMIN_PASSWORD` from `backend/app/core/config.py`. Public user registration endpoints must **not** exist.
2. **Ephemeral Email Privacy:**
   - Never add an email column to any SQLAlchemy model.
   - Never log `notify_email_once` in `logging` or OpenTelemetry span attributes.
   - Store pending one-time notification emails exclusively in the in-memory `EphemeralNotificationRegistry` (`backend/app/services/notification_service.py`) and `pop()` them immediately upon completion or error.
3. **SSRF Guard in Deployment Monitor:**
   - Before making any `httpx` request to a project's `deployment_url`, resolve the hostname via `socket.getaddrinfo` and reject any IP that is private (`is_private`), loopback (`is_loopback`), link-local (`is_link_local`), multicast, or reserved (`169.254.169.254`, `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `::1`).
   - Disable automatic redirects to untrusted internal hosts or re-validate every redirect target.
4. **Score State & Override Preservation:**
   - Updating a criterion score via `PATCH /api/v1/projects/{project_id}/scorecard/{criterion_assessment_id}` must set `human_override_points`, `human_override_reason`, and `score_state`, while leaving `ai_proposed_points` and `ai_reasoning` untouched.
5. **Subtask Decoupling:**
   - Updating `DevelopmentMilestone.status` to `completed` must recalculate `dev_completion_pct`, but must **never** alter `CriterionAssessment.ai_proposed_points` or `human_override_points`.

