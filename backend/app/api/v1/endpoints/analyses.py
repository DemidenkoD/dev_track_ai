"""Analysis run endpoints + ephemeral one-time notification handling.

PRIVACY INVARIANT: `notify_email_once` is NEVER written to PostgreSQL,
never logged, and never placed in tracing spans. It is staged strictly via
Track 3's `notification_service.queue_notification()` into the volatile
in-memory `EPHEMERAL_NOTIFICATIONS` registry keyed by analysis_run_id and
popped by the dispatcher immediately upon send/fail. If an email is supplied
without `acknowledge_ephemeral_email=True`, the request is rejected (400).
This module holds NO local email map (single source of truth lives in the
notification service) and re-exports it only so the worker shares one map.

`ephemeral_notification_queued` SEMANTICS: True means the address was
staged in THIS API process's volatile memory only — it is NOT a delivery
guarantee (SMTP may still be unconfigured/unreachable and the send may
fail or never run). See the cross-process note on `trigger_analysis`.

CROSS-PROCESS CAVEAT (Track 1 scope, read-only for Track 3/docker):
`EPHEMERAL_NOTIFICATIONS` is a process-local Python object. In single-
process dev (tests, `uvicorn` + in-process consumer) the API and the
sender share one registry, so a staged entry is visible. In Docker the
API container and the worker container are SEPARATE processes with
separate registries — an entry staged by the API is invisible to the
worker and can never be delivered. Do NOT fix this by persisting the
email to Postgres (forbidden by AGENTS.md §2.2). A compliant handoff must
stay volatile (see Track 1 return note: API-process polling send or an
internal volatile POST relay).

OPTION A (implemented below): after staging, the POST handler schedules a
FastAPI `BackgroundTasks` entry that spawns a daemon thread in THIS API
process. The thread polls `analysis_runs.status` with a fresh DB session
per poll (interval = WORKER_POLL_INTERVAL_SECONDS, timeout =
ANALYSIS_TIMEOUT_SECONDS, both read-only from config) and, once the run
reaches a terminal state (completed/failed) or the timeout expires, calls
Track 3's `send_and_purge()` with the DEFAULT registry — the same memory
where `queue_notification()` staged the address. Thread (not inline poll)
because Starlette awaits BackgroundTasks before releasing the TestClient /
worker slot: a 300 s inline poll would block the POST response in tests
and exhaust uvicorn workers in prod. The daemon thread decouples delivery
from the request lifecycle.

RESTART / MULTI-WORKER RISK (documented, not fixed here — needs Track 6):
a process restart wipes the dict (staged-but-unsent entries are lost by
design, never persisted); multi-worker uvicorn (`--workers N`) gives each
worker its own dict, so a run polled in worker B cannot see an address
staged in worker A. Mitigations belong to Track 6: run `--workers 1` for
the API, or sticky-route, or an internal volatile relay. Double-send is
impossible: `send_and_purge` pop-once purges, so a worker-side fallback
send (if Track 3 ever adds one) is a harmless no-op.
"""

import threading
import time
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.helpers import get_project_or_404
from app.core.deps import get_current_user, get_db
from app.models.models import AnalysisRun, Project, Rubric
from app.schemas.api_contracts import (
    AnalysisRunSchema,
    TriggerAnalysisRequest,
    UserProfileSchema,
)
from app.schemas.enums import AnalysisStatus, AnalysisTriggerType
from app.services.notification_service import (
    EPHEMERAL_NOTIFICATIONS,
    queue_notification,
    send_and_purge,
)

try:  # Track 3 pure builder (Option A contract); fallback to inline below.
    from app.services.notification_service import (
        build_completion_subject_and_body as _track3_builder,
    )
except Exception:  # pragma: no cover - Track 3 builder not yet present
    _track3_builder = None  # type: ignore[assignment]

router = APIRouter(tags=["analyses"])

# Re-exported for the Track 3 worker: single shared volatile registry.
# (No address is ever logged, traced, or persisted here.)
__all__ = ["router", "EPHEMERAL_NOTIFICATIONS"]


def _build_subject_body(status: str, project_name: str) -> tuple[str, str]:
    """Subject/body via Track 3 builder, inline fallback if unavailable.

    Pure + volatile-only: takes no email address (the recipient stays only
    in the in-memory registry consumed by `send_and_purge`). Never logs.
    """
    if _track3_builder is not None:
        try:
            return _track3_builder(status, project_name)
        except Exception:
            pass
    normalized = (status or "").strip().lower() or "completed"
    project = (project_name or "").strip() or "DevTrack AI"
    return (
        f"{project} analysis {normalized}",
        (
            f"Your {project} analysis run finished with status: {normalized}.\n"
            "View your scorecard and recommendations in the DevTrack AI UI.\n"
            "AI estimates are advisory and never official course grades."
        ),
    )


def _poll_and_send_same_process(
    run_id: UUID, project_id: UUID, project_name: str
) -> None:
    """Daemon-thread body: poll run status, then send+purge in this process.

    Uses a fresh `SessionLocal()` per poll (request `db` session is closed
    by then). Terminal states: completed/failed. On timeout the entry is
    still sent+purged (purge-first, so no leak) and a warning is logged.
    Logs carry run/project ids + booleans + SMTP host category only — never
    the address or secrets. A restart loses the dict by design (volatile).
    """
    from app.core.telemetry import logger as telemetry_logger

    try:
        from app.core.config import get_settings as _get_settings

        _settings = _get_settings()
        interval = max(1, int(_settings.WORKER_POLL_INTERVAL_SECONDS))
        timeout = max(1, int(_settings.ANALYSIS_TIMEOUT_SECONDS))
    except Exception:
        interval, timeout = 5, 300

    status_str = "unknown"
    timed_out = False
    try:
        from app.db.session import SessionLocal as _SessionLocal
    except Exception:  # pragma: no cover - session factory unavailable
        _SessionLocal = None  # type: ignore[assignment]

    deadline = time.monotonic() + timeout
    if _SessionLocal is not None:
        while True:
            poll_db = _SessionLocal()
            try:
                run = poll_db.get(AnalysisRun, run_id)
                if run is not None:
                    raw = getattr(run.status, "value", run.status)
                    status_str = str(raw).strip().lower()
                    if status_str in (
                        AnalysisStatus.COMPLETED.value,
                        AnalysisStatus.FAILED.value,
                    ):
                        break
            except Exception:
                # Transient DB error: keep polling until the deadline.
                status_str = "unknown"
            finally:
                try:
                    poll_db.close()
                except Exception:
                    pass
            if time.monotonic() >= deadline:
                timed_out = True
                break
            remaining = deadline - time.monotonic()
            time.sleep(min(interval, max(0.1, remaining)))
    else:  # pragma: no cover - no session factory; purge without waiting
        timed_out = True

    # Metrics visibility fix (cross-process counter bug): worker/runner.py
    # increments analysis_runs_failed_total in WORKER process memory, but
    # Prometheus scrapes backend:8000 /metrics (BACKEND process memory, always
    # 0), so AnalysisWorkerJobFailures could never fire. This poll loop runs
    # in the backend/API process, so recording the outcome here makes the
    # backend counter visible to Prometheus. Called exactly once per run
    # (timeout path counts as ok=False); never double-count in this process.
    try:
        from app.core.telemetry import record_analysis_run_outcome as _record_outcome

        _record_outcome(status_str == AnalysisStatus.COMPLETED.value)
    except Exception:
        pass

    if timed_out:
        # Purge-first send_and_purge guarantees no leak even on timeout.
        telemetry_logger.warning(
            "ephemeral_notification_poll_timeout analysis_run_id=%s "
            "project_id=%s status=%s (purging via send_and_purge anyway)",
            run_id,
            project_id,
            status_str,
        )

    subject, body_text = _build_subject_body(status_str, project_name)
    try:
        # Default registry = this API process's memory (where staged).
        notified = bool(send_and_purge(run_id, subject, body_text))
    except Exception as exc:  # never raise out of a daemon thread
        telemetry_logger.warning(
            "ephemeral_notification_send_error analysis_run_id=%s "
            "project_id=%s notified=False error_type=%s",
            run_id,
            project_id,
            type(exc).__name__,
        )
        return
    try:
        from app.core.config import get_settings as _get_settings2

        smtp_warn = _get_settings2().smtp_config_warning
        smtp_category = "ok" if smtp_warn is None else "placeholder_or_missing"
    except Exception:
        smtp_category = "unknown"
    (telemetry_logger.info if notified else telemetry_logger.warning)(
        "ephemeral_notification_delivered analysis_run_id=%s project_id=%s "
        "notified=%s smtp=%s status=%s timed_out=%s",
        run_id,
        project_id,
        notified,
        smtp_category,
        status_str,
        timed_out,
    )


def _deliver_ephemeral_after_completion(
    run_id: UUID, project_id: UUID, project_name: str
) -> None:
    """BackgroundTasks entry: spawn the SAME-process polling daemon thread.

    Returns immediately so the 202 response is never delayed (Starlette
    awaits BackgroundTasks before completing the request). The daemon
    thread owns polling + send_and_purge; process restart loses the staged
    entry by design (zero persistent email).
    """
    worker = threading.Thread(
        target=_poll_and_send_same_process,
        args=(run_id, project_id, project_name),
        name=f"ephemeral-notify-{run_id}",
        daemon=True,
    )
    worker.start()


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
    background_tasks: BackgroundTasks,
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
        trigger_type=AnalysisTriggerType.MANUAL,
        status=AnalysisStatus.QUEUED,
        previous_commit_sha=previous.commit_sha if previous else None,
        max_total_points=rubric.max_points if rubric else 24,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    # SMTP readiness check at trigger time (no secrets, no address logged).
    # Warn when the deploy still ships placeholder credentials so the 202
    # `ephemeral_notification_queued=true` flag is not misread as "will be
    # delivered": it only means "staged in this process memory".
    smtp_warning: str | None = None
    if body.notify_email_once is not None:
        try:
            from app.core.config import get_settings as _get_settings

            smtp_warning = _get_settings().smtp_config_warning
        except Exception:
            smtp_warning = None
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
        except ValueError as exc:
            # queue_notification raises ValueError for TWO distinct reasons;
            # surface distinct messages so callers can tell them apart.
            # (Pydantic EmailStr format failures are rejected earlier as 422;
            # this branch covers the registry-level sanity check.)
            message = str(exc).lower()
            if "acknowledge" in message:
                raise HTTPException(
                    status_code=400,
                    detail="acknowledge_ephemeral_email must be true when notify_email_once is provided",
                )
            raise HTTPException(
                status_code=400,
                detail="Invalid one-time notification email address.",
            )
    from app.core.telemetry import get_current_trace_id, logger as telemetry_logger

    if smtp_warning is not None and notified:
        # No address, no secret values — only the config category + ids.
        telemetry_logger.warning(
            "smtp_not_configured analysis_run_id=%s project_id=%s "
            "ephemeral_notification_queued=%s reason=%s trace_id=%s "
            "(staged in this process memory only, not delivered; "
            "cross-process worker containers cannot see this entry)",
            run.id,
            project.id,
            notified,
            smtp_warning,
            get_current_trace_id(),
        )
    elif notified:
        # Same-process vs cross-process hint (debug-level to avoid noise):
        # delivery requires a consumer sharing THIS process's registry.
        telemetry_logger.info(
            "ephemeral_notification_staged analysis_run_id=%s project_id=%s "
            "ephemeral_notification_queued=True trace_id=%s "
            "(volatile, this-process-only; separate worker containers "
            "cannot see this entry)",
            run.id,
            project.id,
            get_current_trace_id(),
        )
    telemetry_logger.info(
        "analysis_run_queued analysis_run_id=%s project_id=%s ephemeral_notification_queued=%s trace_id=%s",
        run.id,
        project.id,
        notified,
        get_current_trace_id(),
    )
    if notified:
        # Option A: SAME-process delivery. The daemon thread polls with
        # fresh sessions and calls send_and_purge against THIS process's
        # registry (cross-process worker containers can never see it).
        # 202 shape unchanged: queued=True still means staged-not-delivered.
        background_tasks.add_task(
            _deliver_ephemeral_after_completion,
            run.id,
            project.id,
            (project.name or "DevTrack AI"),
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
