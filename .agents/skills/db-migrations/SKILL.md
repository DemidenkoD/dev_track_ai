---
name: db-migrations
description: >-
  Manage SQLAlchemy 2.0 database models, schema evolution, and built-in rubric
  seeding for DevTrack AI. Use this skill when creating or modifying tables in
  backend/app/models/ or updating docs/specs/DATABASE_SCHEMA.md.
---

# Database Schema & Seeding Skill

Follow this workflow when adding or modifying SQLAlchemy 2.0 models in `backend/app/models/`.

## Steps

1. **Check Schema Specification**:
   Verify all table and column definitions against [DATABASE_SCHEMA.md](../../../docs/specs/DATABASE_SCHEMA.md).
2. **Enforce Domain Constraints**:
   - **Zero Persistent Email Storage:** Never add an email column to `projects`, `analysis_runs`, or any other table.
   - **Rubric Immutability:** `rubrics` and `rubric_criteria` rows are versioned (`version` field). Never overwrite criteria in place if projects already reference that rubric version.
   - **Milestone Separation:** Keep `assessment_milestones` (official rubric criteria) and `development_milestones` (actionable tasks) in separate tables.
3. **Verify Built-In Rubric Seeding**:
   Ensure startup seeding loads [ai_dev_tools_zoomcamp_2026.json](../../../docs/rubrics/ai_dev_tools_zoomcamp_2026.json) with 12 criteria, 24 max points, and a 10-point passing threshold.

