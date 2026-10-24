"""Track 1 database package: Base, engine/session factory, startup init + seeding.

Schema evolution: Alembic (`backend/alembic.ini` + `backend/alembic/env.py`,
`target_metadata` = `app.db.base.Base.metadata` covering all 13 tables).
Migrate production with `cd backend && alembic upgrade head`.
`init_db.create_all()` is retained as a boot fallback for local/tests only.
"""