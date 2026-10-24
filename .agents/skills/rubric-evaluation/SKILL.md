---
name: rubric-evaluation
description: >-
  Evaluate repository evidence against official course rubrics (including the
  12-criterion DataTalksClub AI Dev Tools Zoomcamp 2026 scorecard) using
  structured Gemini outputs. Use this skill when implementing or debugging
  RubricAnalyst, ProgressAnalyst, or scorecard evaluation logic.
---

# Rubric Evaluation & Evidence Grounding Skill

Use this workflow when building or updating `backend/app/agents/rubric_analyst.py` and `backend/app/services/rubric_service.py`.

## Steps

1. **Load Versioned Official Rubric**:
   Always load the exact `scoring_levels` from [ai_dev_tools_zoomcamp_2026.json](../../../docs/rubrics/ai_dev_tools_zoomcamp_2026.json) or the database `RubricCriterion` record. Never invent point thresholds or custom criteria descriptions.
2. **Map Evidence Items First**:
   Before calling Gemini, gather concrete `EvidenceItem` records (commits, `README.md`, `docs/`, `.github/workflows/*.yml`, `docker-compose.yml`, test files, OpenTelemetry configs, deployment check status).
3. **Enforce Structured Output Schema**:
   Pass `ScorecardEvaluationOutput` as `response_schema` in `google-genai` `GenerateContentConfig`.
4. **Assign Score States Accurately**:
   - `verified`: Concrete, unambiguous deterministic evidence satisfies the scoring level.
   - `estimated`: AI proposes a score based on partial or static code evidence.
   - `needs_review`: Evidence is missing, contradictory, or requires live runtime verification (`ai_confidence < 0.70`).
5. **Preserve Human Overrides**:
   When re-evaluating or displaying a scorecard, never overwrite a human reviewer's `human_override_points` without keeping `ai_proposed_points` and `ai_reasoning` intact.

