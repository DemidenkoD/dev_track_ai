---
name: api-contract-sync
description: >-
  Synchronize OpenAPI 3.1 REST contracts between docs/specs/API_CONTRACT.md,
  backend/app/schemas/api_contracts.py, and frontend/src/types/api.ts. Use this
  skill whenever adding or modifying API endpoints, request bodies, or response
  models across parallel backend and frontend tracks.
---

# API Contract Synchronization Skill

To prevent breaking changes when multiple agents work simultaneously on the FastAPI backend and React + TypeScript frontend, follow this strict contract synchronization procedure.

## Steps

1. **Update Specification First**:
   Document the endpoint path, HTTP method, query parameters, request body, and response payload in [API_CONTRACT.md](../../../docs/specs/API_CONTRACT.md).
2. **Update Backend Pydantic Schemas**:
   Add or update the corresponding Pydantic v2 models in `backend/app/schemas/api_contracts.py`.
3. **Update Frontend TypeScript Interfaces**:
   Mirror the exact field names and types in `frontend/src/types/api.ts`.
4. **Verify Non-Negotiable Contract Rules**:
   - `ScorecardResponse` and `CriterionAssessmentSchema` must always expose both `ai_proposed_points` and `human_override_points` alongside `score_state` (`estimated`, `verified`, `needs_review`).
   - `TriggerAnalysisRequest` may accept `notify_email_once`, but no response schema (`AnalysisRunSchema`, `ProjectDetailSchema`) may ever return an email address.
5. **Validate**:
   Run backend schema validation (`pytest backend/tests/`) and frontend typecheck (`npm --prefix frontend run typecheck`).

