"""Analysis run endpoints + ephemeral one-time notification handling.

PRIVACY INVARIANT: `notify_email_once` is NEVER written to PostgreSQL,
never logged, and never placed in tracing spans. It is held strictly in the
volatile in-memory `EPHEMERAL_NOTIFICATIONS` map keyed by analysis_run_id
(the API-side holding map; Track 3's notification_service owns dispatch and
pops the entry immediately upon send/fail). If an email is supplied without
`acknowledge_ephemeral_email=True`, the request is rejected (400).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.helpers import get_project_or_404
from app.core.deps import get_current_user, get_db
from app.models.models import AnalysisRun, Project, Rubric
from app.schemas.api_contracts import (
    AnalysisRunSchema,
    TriggerAnalysisRequest,
    UserProfileSchema,
)

router = APIRouter(tags=["analyses"])

# Volatile RAM only: analysis_run_id (str) -> one-time recipient email.
# Never persisted, never logged. Popped by the dispatcher after send/fail.
EPHEMERAL_NOTIFICATIONS: dict[str, str] = {}


def _to_schema(run: AnalysisRun, notified: bool = False) -> AnalysisRunSchema:
    return AnalysisRunSchema(
        id=run.id,
        project_id=run.project_id,
        trigger_type=run.trigger_type,
        status=run.status,
        commit_sha=run.commit_sha,
        previous_commit_sha=run.previous_commit_sha,
        estimated_total_points=run.estimated_total_points,
        verified_total_points=run.verified_total_points,
        max_total_points=run.max_total_points,
        dev_completion_pct=run.dev_completion_pct,
        summary_markdown=run.summary_markdown,
        stalled_flag=run.stalled_flag,
        scope_creep_flag=run.scope_creep_flag,
        ephemeral_notification_queued=notified,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )


@router.post(
    "/projects/{project_id}/analyses",
    response_model=AnalysisRunSchema,
    status_code=202,
)
def trigger_analysis(
    project_id: UUID,
    body: TriggerAnalysisRequest,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> AnalysisRunSchema:
    project: Project = get_project_or_404(db, project_id)
    if body.notify_email_once is not None and not body.acknowledge_ephemeral_email:
        raise HTTPException(
            status_code=400,
            detail="acknowledge_ephemeral_email must be true when notify_email_once is provided",
        )
    rubric = db.get(Rubric, project.rubric_id)
    previous = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.project_id == project.id)
        .order_by(AnalysisRun.created_at.desc())
        .first()
    )
    run = AnalysisRun(
        project_id=project.id,
        trigger_type="manual",
        status="queued",
        previous_commit_sha=previous.commit_sha if previous else None,
        max_total_points=rubric.max_points if rubric else 24,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    # Hold the address in volatile memory only (never in the row, never logged).
    notified = False
    if body.notify_email_once is not None:
        EPHEMERAL_NOTIFICATIONS[str(run.id)] = str(body.notify_email_once)
        notified = True
    return _to_schema(run, notified=notified)


@router.get(
    "/projects/{project_id}/analyses", response_model=list[AnalysisRunSchema]
)
def list_analyses(
    project_id: UUID,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> list[AnalysisRunSchema]:
    project = get_project_or_404(db, project_id)
    runs = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.project_id == project.id)
        .order_by(AnalysisRun.created_at.desc())
        .all()
    )
    return [
        _to_schema(r, notified=str(r.id) in EPHEMERAL_NOTIFICATIONS) for r in runs
    ]


@router.get(
    "/projects/{project_id}/analyses/{analysis_run_id}",
    response_model=AnalysisRunSchema,
)
def get_analysis(
    project_id: UUID,
    analysis_run_id: UUID,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> AnalysisRunSchema:
    project = get_project_or_404(db, project_id)
    run = db.get(AnalysisRun, analysis_run_id)
    if run is None or run.project_id != project.id:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return _to_schema(run, notified=str(run.id) in EPHEMERAL_NOTIFICATIONS)
