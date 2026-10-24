"""Assessment + Development milestone endpoints.

INVARIANT — subtask decoupling: PATCHing a development milestone to
`completed` recalculates dev_completion_pct on the latest analysis run ONLY
and must NEVER touch criterion_assessments (no auto-awarding of official
assessment points). The code path below deliberately never queries or
writes CriterionAssessment.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.helpers import (
    assessment_with_code,
    get_project_or_404,
    latest_run,
)
from app.core.deps import get_current_user, get_db
from app.models.models import AssessmentMilestone, DevelopmentMilestone
from app.schemas.api_contracts import (
    AssessmentMilestoneSchema,
    DevelopmentMilestoneCreateRequest,
    DevelopmentMilestoneSchema,
    DevelopmentMilestoneUpdateRequest,
    MilestoneApprovalRequest,
    ProjectMilestonesResponse,
    UserProfileSchema,
)
from app.schemas.enums import DevelopmentMilestoneStatus, MilestoneSource

router = APIRouter(tags=["milestones"])


def _to_dev_schema(d: DevelopmentMilestone) -> DevelopmentMilestoneSchema:
    return DevelopmentMilestoneSchema(
        id=d.id,
        project_id=d.project_id,
        assessment_milestone_id=d.assessment_milestone_id,
        title=d.title,
        description=d.description,
        status=d.status,
        source=d.source,
        is_approved=d.is_approved,
        due_date=d.due_date,
        estimated_effort_hours=d.estimated_effort_hours,
        display_order=d.display_order,
        completed_at=d.completed_at,
    )


@router.get(
    "/projects/{project_id}/milestones", response_model=ProjectMilestonesResponse
)
def get_milestones(
    project_id: UUID,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> ProjectMilestonesResponse:
    project = get_project_or_404(db, project_id)
    dev_by_parent: dict[UUID, list[DevelopmentMilestoneSchema]] = {}
    for d in (
        db.query(DevelopmentMilestone)
        .filter(DevelopmentMilestone.project_id == project.id)
        .order_by(DevelopmentMilestone.display_order)
        .all()
    ):
        dev_by_parent.setdefault(d.assessment_milestone_id, []).append(
            _to_dev_schema(d)
        )
    assessments = [
        AssessmentMilestoneSchema(
            id=am.id,
            project_id=am.project_id,
            rubric_criterion_id=am.rubric_criterion_id,
            criterion_code=code,
            title=am.title,
            max_points=am.max_points,
            target_date=am.target_date,
            is_approved=am.is_approved,
            display_order=am.display_order,
            development_milestones=dev_by_parent.get(am.id, []),
        )
        for am, code, _name, _levels in assessment_with_code(db, project.id)
    ]
    return ProjectMilestonesResponse(
        project_id=project.id,
        milestones_approved=project.milestones_approved,
        assessment_milestones=assessments,
    )


@router.post("/projects/{project_id}/milestones/approve")
def approve_milestones(
    project_id: UUID,
    body: MilestoneApprovalRequest,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> ProjectMilestonesResponse:
    project = get_project_or_404(db, project_id)
    if body.approve_all:
        db.query(AssessmentMilestone).filter(
            AssessmentMilestone.project_id == project.id
        ).update({"is_approved": True})
        db.query(DevelopmentMilestone).filter(
            DevelopmentMilestone.project_id == project.id
        ).update({"is_approved": True})
    else:
        if body.assessment_milestone_ids:
            db.query(AssessmentMilestone).filter(
                AssessmentMilestone.project_id == project.id,
                AssessmentMilestone.id.in_(body.assessment_milestone_ids),
            ).update({"is_approved": True}, synchronize_session=False)
        if body.development_milestone_ids:
            db.query(DevelopmentMilestone).filter(
                DevelopmentMilestone.project_id == project.id,
                DevelopmentMilestone.id.in_(body.development_milestone_ids),
            ).update({"is_approved": True}, synchronize_session=False)
    project.milestones_approved = True
    db.commit()
    return get_milestones(project_id, db, _user)


def _recalculate_dev_completion(db: Session, project_id: UUID) -> float:
    """Development completion % from development_milestones only.

    Mirrors helpers.build_development_progress; writes the value onto the
    latest analysis run for snapshot convenience. NEVER touches
    criterion_assessments — see module docstring.
    """
    tasks = (
        db.query(DevelopmentMilestone)
        .filter(DevelopmentMilestone.project_id == project_id)
        .all()
    )
    if not tasks:
        return 0.0
    done = sum(1 for t in tasks if t.status == DevelopmentMilestoneStatus.COMPLETED)
    pct = round(done / len(tasks) * 100.0, 1)
    run = latest_run(db, project_id)
    if run is not None:
        run.dev_completion_pct = pct
    return pct


@router.post(
    "/projects/{project_id}/development-milestones",
    response_model=DevelopmentMilestoneSchema,
    status_code=201,
)
def create_development_milestone(
    project_id: UUID,
    body: DevelopmentMilestoneCreateRequest,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> DevelopmentMilestoneSchema:
    project = get_project_or_404(db, project_id)
    parent = db.get(AssessmentMilestone, body.assessment_milestone_id)
    if parent is None or parent.project_id != project.id:
        raise HTTPException(
            status_code=400,
            detail="assessment_milestone_id must belong to this project",
        )
    order = (
        db.query(DevelopmentMilestone)
        .filter(
            DevelopmentMilestone.assessment_milestone_id == parent.id,
        )
        .count()
    )
    dev = DevelopmentMilestone(
        project_id=project.id,
        assessment_milestone_id=parent.id,
        title=body.title,
        description=body.description,
        status=DevelopmentMilestoneStatus.OUTSTANDING,
        source=MilestoneSource.USER_CREATED,
        is_approved=project.milestones_approved,
        due_date=body.due_date,
        estimated_effort_hours=body.estimated_effort_hours,
        display_order=order,
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)
    _recalculate_dev_completion(db, project.id)
    db.commit()
    db.refresh(dev)
    return _to_dev_schema(dev)


@router.patch(
    "/projects/{project_id}/development-milestones/{dev_milestone_id}",
    response_model=DevelopmentMilestoneSchema,
)
def update_development_milestone(
    project_id: UUID,
    dev_milestone_id: UUID,
    body: DevelopmentMilestoneUpdateRequest,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> DevelopmentMilestoneSchema:
    project = get_project_or_404(db, project_id)
    dev = db.get(DevelopmentMilestone, dev_milestone_id)
    if dev is None or dev.project_id != project.id:
        raise HTTPException(status_code=404, detail="Development milestone not found")
    data = body.model_dump(exclude_unset=True)
    if "title" in data and data["title"] is not None:
        dev.title = data["title"]
    if "description" in data:
        dev.description = data["description"]
    if "due_date" in data:
        dev.due_date = data["due_date"]
    if "estimated_effort_hours" in data:
        dev.estimated_effort_hours = data["estimated_effort_hours"]
    if data.get("status") is not None:
        dev.status = data["status"]
        if dev.status == DevelopmentMilestoneStatus.COMPLETED:
            dev.completed_at = datetime.now(timezone.utc)
        else:
            dev.completed_at = None
    db.commit()
    # Recalculate dev completion ONLY — no assessment score mutation here.
    _recalculate_dev_completion(db, project.id)
    db.commit()
    db.refresh(dev)
    return _to_dev_schema(dev)
