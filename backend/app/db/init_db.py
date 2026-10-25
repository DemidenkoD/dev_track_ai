"""Startup DB init + built-in rubric seeding (db-migrations skill workflow).

- Creates all tables (Base.metadata.create_all).
- Seeds the DataTalksClub AI Dev Tools Zoomcamp 2026 rubric from
  docs/rubrics/ai_dev_tools_zoomcamp_2026.json (12 criteria, 24 max points,
  10-point passing threshold) if the matching slug+version is absent.
- Seeds the DevTrack AI repo itself as a default example tracked project.
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

EXAMPLE_PROJECT_URL = "https://github.com/DemidenkoD/dev_track_ai"
EXAMPLE_DEPLOYMENT_URL = "https://ct-academia.pl"


def _normalize_github_url(url: str) -> str:
    """Strip whitespace, trailing slashes, and a trailing `.git` suffix."""
    normalized = (url or "").strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[: -len(".git")].rstrip("/")
    return normalized


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


def seed_example_project(db: Session) -> None:
    """Seed DevTrack AI itself as the default example tracked project.

    Idempotent: returns without changes if a project whose normalized
    ``github_repo_url`` already matches the example repo URL exists.
    Mirrors the POST /api/v1/projects creation loop (draft assessment
    milestones + one initial queued analysis run) without awarding any
    assessment points or creating development milestones.
    """
    from app.models.models import (
        AnalysisRun,
        AssessmentMilestone,
        Project,
        Rubric,
        RubricCriterion,
    )
    from app.schemas.enums import (
        AnalysisStatus,
        AnalysisTriggerType,
        ProjectStatus,
    )

    # Ensure the built-in rubric exists before looking it up.
    seed_builtin_rubric(db)
    rubric = (
        db.query(Rubric)
        .filter(Rubric.slug == "ai-dev-tools-zoomcamp-2026")
        .order_by(Rubric.created_at.desc())
        .first()
    )
    if rubric is None:
        logger.warning("Example project seeding skipped: built-in rubric missing")
        return

    target = _normalize_github_url(EXAMPLE_PROJECT_URL)
    for (existing_url,) in db.query(Project.github_repo_url).all():
        if _normalize_github_url(existing_url) == target:
            return

    criteria = (
        db.query(RubricCriterion)
        .filter(RubricCriterion.rubric_id == rubric.id)
        .order_by(RubricCriterion.display_order)
        .all()
    )

    project = Project(
        name="DevTrack AI",
        description="AI mentor from project idea to deployment — self-tracked example.",
        github_repo_url=EXAMPLE_PROJECT_URL,
        github_owner="DemidenkoD",
        github_repo="dev_track_ai",
        default_branch="main",
        course_name="AI Dev Tools Zoomcamp 2026",
        rubric_id=rubric.id,
        status=ProjectStatus.ACTIVE,
        weekly_hours=10,
        diary_path=None,
        deployment_url=EXAMPLE_DEPLOYMENT_URL,
        daily_schedule_cron="0 6 * * *",
        milestones_approved=False,
    )
    db.add(project)
    db.flush()
    # Draft assessment milestones from official criteria (unapproved gate).
    for i, c in enumerate(criteria):
        db.add(
            AssessmentMilestone(
                project_id=project.id,
                rubric_criterion_id=c.id,
                title=c.name,
                max_points=c.max_points,
                is_approved=False,
                display_order=c.display_order or i,
            )
        )
    # Seed an initial queued analysis run row (Track 3 worker picks it up).
    db.add(
        AnalysisRun(
            project_id=project.id,
            trigger_type=AnalysisTriggerType.INITIAL,
            status=AnalysisStatus.QUEUED,
            max_total_points=rubric.max_points,
        )
    )
    db.commit()
    logger.info("Seeded example project %s", EXAMPLE_PROJECT_URL)


def normalize_legacy_enum_case(db: Session) -> int:
    """Lowercase legacy uppercase enum NAMEs left by pre-fix ``SqlEnum``.

    Background (Track 1): ``SqlEnum(X, native_enum=False)`` WITHOUT
    ``values_callable`` persisted enum NAMES (``QUEUED``/``MANUAL``/``ACTIVE``)
    as ``VARCHAR``. After the fix (``values_callable=_enum_values`` in
    ``app/models/models.py``) the ORM only deserialises lowercase wire VALUES
    (``queued``/``manual``/``active``), so a legacy row raises
    ``LookupError: 'MANUAL' is not among the defined enum values`` on
    ``session.get(AnalysisRun, ...)`` and the worker's
    ``claim_next_queued_run`` falls through to ``None`` even though
    ``WHERE LOWER(status)='queued'`` still matches at the SQL level.

    This backfill is idempotent (``WHERE col <> LOWER(col)``) and runs on
    every backend startup via :func:`init_db`. It touches only enum case —
    never ``ai_proposed_points``/``human_override_*``, never any email
    (no email column exists). Safe on PostgreSQL and SQLite (``LOWER()``
    works on ``VARCHAR`` on both; no ``::text`` cast needed because the live
    column is ``VARCHAR(32)``, not a native PG ``ENUM``).
    Returns the total rows normalised.
    """
    from sqlalchemy import text

    statements = [
        "UPDATE rubrics SET source_type=LOWER(source_type)"
        " WHERE source_type<>LOWER(source_type)",
        "UPDATE projects SET status=LOWER(status) WHERE status<>LOWER(status)",
        "UPDATE development_milestones SET status=LOWER(status)"
        " WHERE status<>LOWER(status)",
        "UPDATE development_milestones SET source=LOWER(source)"
        " WHERE source<>LOWER(source)",
        "UPDATE analysis_runs SET status=LOWER(status)"
        " WHERE status<>LOWER(status)",
        "UPDATE analysis_runs SET trigger_type=LOWER(trigger_type)"
        " WHERE trigger_type<>LOWER(trigger_type)",
        "UPDATE evidence_items SET evidence_type=LOWER(evidence_type)"
        " WHERE evidence_type<>LOWER(evidence_type)",
        "UPDATE criterion_assessments SET score_state=LOWER(score_state)"
        " WHERE score_state<>LOWER(score_state)",
        "UPDATE security_reports SET overall_status=LOWER(overall_status)"
        " WHERE overall_status<>LOWER(overall_status)",
        "UPDATE security_findings SET severity=LOWER(severity)"
        " WHERE severity<>LOWER(severity)",
        "UPDATE deployment_checks SET discovery_source=LOWER(discovery_source)"
        " WHERE discovery_source<>LOWER(discovery_source)",
        "UPDATE recommendations SET priority=LOWER(priority)"
        " WHERE priority<>LOWER(priority)",
        "UPDATE recommendations SET technical_risk=LOWER(technical_risk)"
        " WHERE technical_risk<>LOWER(technical_risk)",
    ]
    total = 0
    for sql in statements:
        try:
            result = db.execute(text(sql))
            total += int(getattr(result, "rowcount", 0) or 0)
        except Exception as exc:  # missing table on first boot: skip
            logger.debug("Enum case normalisation skipped (%s).", type(exc).__name__)
            try:
                db.rollback()
            except Exception:
                pass
            continue
    try:
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    if total:
        logger.info("Normalised %d legacy uppercase enum value(s) to lowercase", total)
    return total


def init_db() -> None:
    """Create tables and seed the built-in rubric; never raises on failure."""
    try:
        from app.db.session import SessionLocal, engine

        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            normalize_legacy_enum_case(db)
            seed_builtin_rubric(db)
            seed_example_project(db)
        finally:
            db.close()
    except Exception as exc:  # startup must not crash if Postgres is down
        logger.warning("init_db skipped: %s", exc)
