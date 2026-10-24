"""Analysis run endpoints + ephemeral one-time notification handling.

PRIVACY INVARIANT: `notify_email_once` is NEVER written to PostgreSQL,
never logged, and never placed in tracing spans. It is staged strictly via
Track 3's `notification_service.queue_notification()` into the volatile
in-memory `EPHEMERAL_NOTIFICATIONS` registry keyed by analysis_run_id and
popped by the dispatcher immediately upon send/fail. If an email is supplied
without `acknowledge_ephemeral_email=True`, the request is rejected (400).
This module holds NO local email map (single source of truth lives in the
notification service) and re-exports it only so the worker shares one map.
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
from app.services.notification_service import (
    EPHEMERAL_NOTIFICATIONS,
    queue_notification,
)

router = APIRouter(tags=["analyses"])

# Re-exported for the Track 3 worker: single shared volatile registry.
# (No address is ever logged, traced, or persisted here.)
__all__ = ["router", "EPHEMERAL_NOTIFICATIONS"]


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
    # Stage the address in volatile memory only (never in the row, never logged).
    # queue_notification() validates + stores it in the shared registry.
    notified = False
    if body.notify_email_once is not None:
        try:
            notified = queue_notification(
                run.id,
                str(body.notify_email_once),
                acknowledged=body.acknowledge_ephemeral_email,
            )
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="acknowledge_ephemeral_email must be true when notify_email_once is provided",
            )
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
        _to_schema(r, notified=EPHEMERAL_NOTIFICATIONS.has(r.id)) for r in runs
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
    return _to_schema(run, notified=EPHEMERAL_NOTIFICATIONS.has(run.id))
