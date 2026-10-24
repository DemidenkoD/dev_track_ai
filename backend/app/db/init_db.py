"""Startup DB init + built-in rubric seeding (db-migrations skill workflow).

- Creates all tables (Base.metadata.create_all).
- Seeds the DataTalksClub AI Dev Tools Zoomcamp 2026 rubric from
  docs/rubrics/ai_dev_tools_zoomcamp_2026.json (12 criteria, 24 max points,
  10-point passing threshold) if the matching slug+version is absent.
- Idempotent; never overwrites versioned rubric rows in place.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.base import Base

logger = logging.getLogger(__name__)

BUILTIN_RUBRIC_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "rubrics"
    / "ai_dev_tools_zoomcamp_2026.json"
)


def seed_builtin_rubric(db: Session) -> None:
    from app.models.models import Rubric, RubricCriterion
    from app.schemas.enums import RubricSourceType

    try:
        payload = json.loads(BUILTIN_RUBRIC_PATH.read_text())
    except FileNotFoundError:
        logger.warning("Built-in rubric JSON not found at %s", BUILTIN_RUBRIC_PATH)
        return

    slug = payload.get("rubric_id", "ai-dev-tools-zoomcamp-2026")
    version = payload.get("version", "2026.1.0")
    existing = (
        db.query(Rubric).filter(Rubric.slug == slug, Rubric.version == version).first()
    )
    if existing is not None:
        return

    rubric = Rubric(
        slug=slug,
        title=payload["title"],
        course_name=payload["course_name"],
        source_type=RubricSourceType.BUILTIN,
        source_url=payload.get("source_url"),
        raw_content=json.dumps(payload),
        version=version,
        is_official=bool(payload.get("is_official", True)),
        max_points=int(payload.get("max_points", 24)),
        passing_threshold=payload.get("passing_threshold", 10),
    )
    db.add(rubric)
    db.flush()
    for item in payload.get("criteria", []):
        db.add(
            RubricCriterion(
                rubric_id=rubric.id,
                code=item["code"],
                name=item["name"],
                description=item.get("description", ""),
                display_order=int(item.get("display_order", 0)),
                max_points=int(item.get("max_points", 0)),
                scoring_levels=item.get("scoring_levels", []),
                required_evidence_types=item.get("required_evidence_types", []),
            )
        )
    db.commit()
    logger.info("Seeded built-in rubric %s v%s", slug, version)


def init_db() -> None:
    """Create tables and seed the built-in rubric; never raises on failure."""
    try:
        from app.db.session import SessionLocal, engine

        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            seed_builtin_rubric(db)
        finally:
            db.close()
    except Exception as exc:  # startup must not crash if Postgres is down
        logger.warning("init_db skipped: %s", exc)
