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


def _default_dev_task_specs() -> dict[str, dict]:
    """One realistic DevelopmentMilestone spec per rubric criterion code.

    9 x completed, 2 x partial, 1 x outstanding — so Development Progress
    shows meaningful values on a fresh seed while leaving all
    CriterionAssessment scores untouched (never auto-awarded).
    """
    from app.schemas.enums import DevelopmentMilestoneStatus

    Completed = DevelopmentMilestoneStatus.COMPLETED
    Partial = DevelopmentMilestoneStatus.PARTIAL
    Outstanding = DevelopmentMilestoneStatus.OUTSTANDING
    return {
        "problem_description": {
            "title": "Document problem statement and target users",
            "description": "Write docs/PROBLEM_DESCRIPTION.md: who has the problem, why existing approaches fall short, how DevTrack AI solves it.",
            "status": Completed,
            "estimated_effort_hours": 3.0,
        },
        "product_specification": {
            "title": "Maintain product specification with acceptance criteria",
            "description": "Keep docs/PRODUCT_SPEC.md current: features, architecture, data model, security, acceptance criteria.",
            "status": Completed,
            "estimated_effort_hours": 4.0,
        },
        "agent_team_specification": {
            "title": "Define agent team roles and coordination protocol",
            "description": "Maintain docs/specs/AGENT_TEAM_SPEC.md + .agents/agents/ profiles with file ownership and structured outputs.",
            "status": Completed,
            "estimated_effort_hours": 4.0,
        },
        "context_management": {
            "title": "Keep hierarchical AGENTS.md and skills in sync",
            "description": "Maintain scoped AGENTS.md files and modular .agents/skills/ runbooks via progressive disclosure.",
            "status": Completed,
            "estimated_effort_hours": 3.0,
        },
        "application": {
            "title": "Deliver end-to-end app runnable with a single command",
            "description": "FastAPI backend + React frontend + PostgreSQL connected end-to-end; `make up` starts the full stack locally.",
            "status": Completed,
            "estimated_effort_hours": 8.0,
        },
        "testing": {
            "title": "Cover backend pytest and frontend E2E suites",
            "description": "Backend pytest unit/integration tests plus Playwright/Vitest E2E runnable via a single command.",
            "status": Completed,
            "estimated_effort_hours": 6.0,
        },
        "containerization": {
            "title": "Containerize all services with Docker Compose",
            "description": "Dockerfiles for backend/frontend/worker plus docker-compose orchestration of DB, proxy, and observability.",
            "status": Completed,
            "estimated_effort_hours": 5.0,
        },
        "deployment": {
            "title": "Publish live HTTPS deployment with health checks",
            "description": "Live deployment at the configured deployment_url with HTTPS, /health checks, and reviewer access docs in README.",
            "status": Completed,
            "estimated_effort_hours": 4.0,
        },
        "ci_cd": {
            "title": "Maintain CI test and deploy pipeline",
            "description": "GitHub Actions workflow running tests on PRs with build/deploy steps for dev and production.",
            "status": Completed,
            "estimated_effort_hours": 4.0,
        },
        "observability": {
            "title": "Complete Prometheus/Loki/Tempo/Grafana observability",
            "description": "Finish OTLP traces to Tempo, Loki log shipping, Prometheus metrics, and Grafana dashboards; verify in Docker.",
            "status": Partial,
            "estimated_effort_hours": 5.0,
        },
        "alerting_on_user_impact": {
            "title": "Tune user-impact alerting rules",
            "description": "Actionable alerts on HTTP 5xx rate, p95 latency, failed analysis jobs, and endpoint downtime.",
            "status": Partial,
            "estimated_effort_hours": 3.0,
        },
        "on_call_agent": {
            "title": "Harden bounded read-only on-call diagnosis",
            "description": "Read-only On-Call agent over Prometheus/Loki/Tempo with evidence citations and safe remediation runbooks.",
            "status": Outstanding,
            "estimated_effort_hours": 5.0,
        },
    }


def _create_dev_milestones_for_project(db, project, assessment_by_criterion_id, criteria) -> int:
    """Create one DevelopmentMilestone per criterion; returns rows created.

    INVARIANT: touches ONLY development_milestones (+ approval flags).
    Never sets/alters CriterionAssessment.ai_proposed_points or
    human_override_points — completing dev tasks never auto-awards scores.
    """
    from datetime import datetime, timezone

    from app.models.models import DevelopmentMilestone
    from app.schemas.enums import DevelopmentMilestoneStatus, MilestoneSource

    specs = _default_dev_task_specs()
    now = datetime.now(timezone.utc)
    created = 0
    for c in sorted(criteria, key=lambda x: (x.display_order or 0)):
        am = assessment_by_criterion_id.get(c.id)
        if am is None:
            continue
        spec = specs.get(c.code, {})
        status = spec.get("status", DevelopmentMilestoneStatus.OUTSTANDING)
        db.add(
            DevelopmentMilestone(
                project_id=project.id,
                assessment_milestone_id=am.id,
                title=spec.get("title", f"Implement {c.name}"),
                description=spec.get("description", c.description),
                status=status,
                source=MilestoneSource.AI_GENERATED,
                is_approved=True,
                estimated_effort_hours=spec.get("estimated_effort_hours", 3.0),
                display_order=c.display_order or 0,
                completed_at=now if status == DevelopmentMilestoneStatus.COMPLETED else None,
            )
        )
        created += 1
    return created


def seed_example_project(db: Session) -> None:
    """Seed DevTrack AI itself as the default example tracked project.

    Idempotent: if a project whose normalized ``github_repo_url`` already
    matches the example repo URL exists, backfills approval + development
    milestones instead of duplicating. New projects are created with
    approved assessment milestones and 12 development tasks.
    Mirrors the POST /api/v1/projects creation loop (assessment
    milestones + one initial queued analysis run) without awarding any
    assessment points.

    INVARIANT: seeding or completing ``DevelopmentMilestone`` rows MUST
    NEVER set or alter ``CriterionAssessment.ai_proposed_points`` or
    ``human_override_points``.
    """
    from app.models.models import (
        AnalysisRun,
        AssessmentMilestone,
        DevelopmentMilestone,
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

    criteria = (
        db.query(RubricCriterion)
        .filter(RubricCriterion.rubric_id == rubric.id)
        .order_by(RubricCriterion.display_order)
        .all()
    )

    target = _normalize_github_url(EXAMPLE_PROJECT_URL)
    existing_project = None
    for proj in db.query(Project).all():
        if _normalize_github_url(proj.github_repo_url) == target:
            existing_project = proj
            break

    if existing_project is not None:
        # Idempotent backfill: approve + seed dev tasks if none exist.
        # Never touches criterion_assessments (scores stay untouched).
        assessments = (
            db.query(AssessmentMilestone)
            .filter(AssessmentMilestone.project_id == existing_project.id)
            .all()
        )
        for am in assessments:
            am.is_approved = True
        existing_project.milestones_approved = True
        db.flush()
        assessment_by_criterion_id = {am.rubric_criterion_id: am for am in assessments}
        dev_count = (
            db.query(DevelopmentMilestone)
            .filter(DevelopmentMilestone.project_id == existing_project.id)
            .count()
        )
        if dev_count == 0 and assessments:
            created = _create_dev_milestones_for_project(
                db, existing_project, assessment_by_criterion_id, criteria
            )
            db.commit()
            logger.info(
                "Backfilled %d development milestones for example project %s",
                created,
                EXAMPLE_PROJECT_URL,
            )
        else:
            db.commit()
        return

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
        milestones_approved=True,
    )
    db.add(project)
    db.flush()
    # Approved assessment milestones from official criteria.
    for i, c in enumerate(criteria):
        db.add(
            AssessmentMilestone(
                project_id=project.id,
                rubric_criterion_id=c.id,
                title=c.name,
                max_points=c.max_points,
                is_approved=True,
                display_order=c.display_order or i,
            )
        )
    db.flush()
    assessments = (
        db.query(AssessmentMilestone)
        .filter(AssessmentMilestone.project_id == project.id)
        .all()
    )
    assessment_by_criterion_id = {am.rubric_criterion_id: am for am in assessments}
    _create_dev_milestones_for_project(
        db, project, assessment_by_criterion_id, criteria
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
