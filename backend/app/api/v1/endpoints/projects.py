"""Project CRUD + dashboard aggregation.

- POST validates github_repo_url is https://github.com/<owner>/<repo> (400).
- Creation generates DRAFT assessment milestones from the rubric (approval
  gate: milestones_approved=False) so progress tracking starts unapproved.
- Summaries keep Assessment (expected score) vs Development (completion)
  dimensions separate, with advisory disclaimers (never official grades).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.helpers import (
    build_development_progress,
    build_expected_score,
    get_project_or_404,
    latest_run,
    parse_github_url,
)
from app.core.deps import get_current_user, get_db
from app.db.init_db import seed_builtin_rubric
from app.models.models import (
    AnalysisRun,
    AssessmentMilestone,
    DeploymentCheck,
    Project,
    Rubric,
    RubricCriterion,
    SecurityReport,
)
from app.schemas.api_contracts import (
    DashboardOverviewSchema,
    ProjectCreateRequest,
    ProjectDetailSchema,
    ProjectSummarySchema,
    ProjectUpdateRequest,
    UserProfileSchema,
)
from app.schemas.enums import ProjectStatus, SecurityStatus

router = APIRouter(tags=["projects"])
dashboard_router = APIRouter(tags=["dashboard"])


def _project_to_summary(db: Session, p: Project) -> ProjectSummarySchema:
    run = latest_run(db, p.id)
    expected = build_expected_score(db, p, run)
    progress = build_development_progress(db, p)
    sec = (
        db.query(SecurityReport)
        .filter(SecurityReport.project_id == p.id)
        .order_by(SecurityReport.created_at.desc())
        .first()
    )
    dep = (
        db.query(DeploymentCheck)
        .filter(DeploymentCheck.project_id == p.id)
        .order_by(DeploymentCheck.checked_at.desc())
        .first()
    )
    return ProjectSummarySchema(
        id=p.id,
        name=p.name,
        description=p.description,
        github_repo_url=p.github_repo_url,
        github_owner=p.github_owner,
        github_repo=p.github_repo,
        course_name=p.course_name,
        rubric_id=p.rubric_id,
        status=p.status,
        start_date=p.start_date,
        target_date=p.target_date,
        weekly_hours=p.weekly_hours,
        diary_path=p.diary_path,
        deployment_url=p.deployment_url,
        daily_schedule_cron=p.daily_schedule_cron,
        milestones_approved=p.milestones_approved,
        last_analysis_at=p.last_analysis_at,
        last_commit_sha=run.commit_sha if run else None,
        security_status=sec.overall_status if sec else SecurityStatus.WARNING,
        deployment_reachable=dep.is_reachable if dep else None,
        expected_score=expected,
        development_progress=progress,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _project_to_detail(db: Session, p: Project) -> ProjectDetailSchema:
    summary = _project_to_summary(db, p)
    run = latest_run(db, p.id)
    return ProjectDetailSchema(
        **summary.model_dump(),
        latest_summary_markdown=run.summary_markdown if run else None,
        stalled_flag=run.stalled_flag if run else False,
        scope_creep_flag=run.scope_creep_flag if run else False,
    )


@dashboard_router.get("/dashboard", response_model=DashboardOverviewSchema)
def get_dashboard(
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> DashboardOverviewSchema:
    projects = db.query(Project).order_by(Project.created_at).all()
    summaries = [_project_to_summary(db, p) for p in projects]
    active = sum(1 for p in projects if p.status == ProjectStatus.ACTIVE)
    return DashboardOverviewSchema(
        total_projects=len(projects),
        active_projects=active,
        projects=summaries,
    )


@router.get("/projects", response_model=list[ProjectSummarySchema])
def list_projects(
    status: ProjectStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> list[ProjectSummarySchema]:
    q = db.query(Project).order_by(Project.created_at)
    if status is not None:
        q = q.filter(Project.status == status)
    return [_project_to_summary(db, p) for p in q.all()]


@router.post("/projects", response_model=ProjectDetailSchema, status_code=201)
def create_project(
    body: ProjectCreateRequest,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> ProjectDetailSchema:
    parsed = parse_github_url(body.github_repo_url)
    if parsed is None:
        raise HTTPException(
            status_code=400,
            detail="github_repo_url must be a public https://github.com/<owner>/<repo> URL",
        )
    owner, repo = parsed

    rubric: Rubric | None = None
    if body.rubric_id is not None:
        rubric = db.get(Rubric, body.rubric_id)
        if rubric is None:
            raise HTTPException(status_code=400, detail="rubric_id not found")
    else:
        seed_builtin_rubric(db)
        rubric = (
            db.query(Rubric)
            .filter(Rubric.slug == "ai-dev-tools-zoomcamp-2026")
            .order_by(Rubric.created_at.desc())
            .first()
        )
        if rubric is None:
            raise HTTPException(
                status_code=400, detail="No rubric available; provide rubric_id"
            )
    criteria = (
        db.query(RubricCriterion)
        .filter(RubricCriterion.rubric_id == rubric.id)
        .order_by(RubricCriterion.display_order)
        .all()
    )

    project = Project(
        name=body.name,
        description=body.description,
        github_repo_url=body.github_repo_url.strip(),
        github_owner=owner,
        github_repo=repo,
        course_name=body.course_name,
        rubric_id=rubric.id,
        status=ProjectStatus.ACTIVE,
        start_date=body.start_date,
        target_date=body.target_date,
        weekly_hours=body.weekly_hours,
        diary_path=body.diary_path,
        deployment_url=body.deployment_url,
        daily_schedule_cron=body.daily_schedule_cron,
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
            trigger_type="initial",
            status="queued",
            max_total_points=rubric.max_points,
        )
    )
    db.commit()
    db.refresh(project)
    return _project_to_detail(db, project)


@router.get("/projects/{project_id}", response_model=ProjectDetailSchema)
def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> ProjectDetailSchema:
    return _project_to_detail(db, get_project_or_404(db, project_id))


@router.patch("/projects/{project_id}", response_model=ProjectDetailSchema)
def update_project(
    project_id: UUID,
    body: ProjectUpdateRequest,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> ProjectDetailSchema:
    project = get_project_or_404(db, project_id)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return _project_to_detail(db, project)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> Response:
    project = get_project_or_404(db, project_id)
    db.delete(project)  # cascades to milestones/runs/evidence per ORM config
    db.commit()
    return Response(status_code=204)
