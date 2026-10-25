"""PostgreSQL-backed analysis worker (Track 3).

Queue protocol:
    - Manual analyses are enqueued as ``analysis_runs`` rows with
      ``status='queued'`` by the Track 1 API.
    - This worker claims them with ``SELECT ... FOR UPDATE SKIP LOCKED``
      so multiple worker replicas never double-process a run.
    - Active projects also get daily analyses when their
      ``daily_schedule_cron`` is due (hour/minute match) or when they have
      never been analyzed.

Each claimed run executes :func:`process_single_run`, which orchestrates
the deterministic pipeline (GitHub → diary → security → deployment) and
sends any staged ephemeral notification (purged immediately afterwards).

Gemini wiring (Track 3 → Track 2):
    - :func:`process_single_run` auto-resolves a ``score_fn`` via
      :func:`build_gemini_score_fn` when ``is_gemini_configured()`` is true,
      delegating to ``app.agents.rubric_analyst.evaluate_scorecard``.
      All Track 2 imports are lazy (inside functions) so the worker stays
      import-safe offline without a key or network.
    - When no key is configured, ``score_fn=None`` is passed through and
      ``analysis_pipeline`` uses its deterministic 0-point ``needs_review``
      stub — identical behaviour to before.
    - Any Track 2 exception degrades to the stub with a WARNING naming only
      the error class (never secrets).

Public API:
    - :func:`claim_next_queued_run`
    - :func:`schedule_daily_analyses`
    - :func:`process_single_run`
    - :func:`build_gemini_score_fn`
    - :func:`run_once`
    - :func:`run_forever`
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Queue primitives (PostgreSQL SKIP LOCKED with SQLite fallback)
# ---------------------------------------------------------------------------

CLAIM_SQL_POSTGRES = """
SELECT id FROM analysis_runs
WHERE status = 'queued'
ORDER BY created_at ASC
LIMIT 1
FOR UPDATE SKIP LOCKED
"""

CLAIM_SQL_FALLBACK = """
SELECT id FROM analysis_runs
WHERE status = 'queued'
ORDER BY created_at ASC
LIMIT 1
"""


def claim_next_queued_run(session: Any) -> UUID | None:
    """Claim the oldest queued run; return its id or None.

    Uses ``SELECT ... FOR UPDATE SKIP LOCKED`` on PostgreSQL so concurrent
    workers skip locked rows. Falls back to a plain SELECT on SQLite (tests).
    The caller must transition the row to ``running`` inside the same
    transaction and commit.
    """
    from sqlalchemy import text

    bind = session.get_bind() if hasattr(session, "get_bind") else None
    dialect = getattr(getattr(bind, "dialect", None), "name", "sqlite")
    sql = CLAIM_SQL_POSTGRES if dialect == "postgresql" else CLAIM_SQL_FALLBACK
    try:
        row = session.execute(text(sql)).first()
    except Exception:
        # Postgres executemany edge / locked-row contention: treat as empty.
        session.rollback()
        return None
    if not row:
        return None
    raw_id = row[0]
    run_id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
    run = _get_run(session, run_id)
    if run is None or str(getattr(run, "status", "")) != "queued":
        return None
    run.status = _analysis_status("running")
    run.started_at = _utcnow()
    session.flush()
    return run_id


def schedule_daily_analyses(session: Any, *, now: datetime | None = None) -> int:
    """Enqueue daily analyses for due active projects. Returns rows created."""
    from sqlalchemy import text

    moment = now or _utcnow()
    try:
        rows = session.execute(
            text(
                "SELECT id, daily_schedule_cron, last_analysis_at "
                "FROM projects WHERE status = 'active'"
            )
        ).all()
    except Exception as exc:
        logger.warning("Daily scheduling query failed (%s).", type(exc).__name__)
        return 0
    created = 0
    for project_id_raw, cron, last_at in rows:
        try:
            if not _cron_due_today(str(cron or "0 6 * * *"), moment, last_at):
                continue
            project_id = (
                project_id_raw if isinstance(project_id_raw, UUID) else UUID(str(project_id_raw))
            )
            if _has_pending_run(session, project_id):
                continue
            session.execute(
                text(
                    "INSERT INTO analysis_runs (id, project_id, trigger_type, status, created_at) "
                    "VALUES (gen_random_uuid(), :pid, 'daily', 'queued', now())"
                ),
                {"pid": str(project_id)},
            )
            created += 1
        except Exception:
            # Portable fallback for SQLite test DBs (no gen_random_uuid/now()).
            try:
                import uuid as _uuid

                session.execute(
                    text(
                        "INSERT INTO analysis_runs (id, project_id, trigger_type, status) "
                        "VALUES (:rid, :pid, 'daily', 'queued')"
                    ),
                    {"rid": str(_uuid.uuid4()), "pid": str(project_id)},
                )
                created += 1
            except Exception as exc:
                logger.warning("Failed to enqueue daily run (%s).", type(exc).__name__)
                continue
    try:
        session.commit()
    except Exception:
        session.rollback()
    return created


def _cron_due_today(cron: str, now: datetime, last_at: Any) -> bool:
    """Minimal cron check: minute+hour match and no run in the last 20h."""
    try:
        parts = cron.strip().split()
        if len(parts) < 2:
            return _stale(last_at, now)
        minute_s, hour_s = parts[0], parts[1]
        minute_ok = minute_s == "*" or int(minute_s) == now.minute
        hour_ok = hour_s == "*" or int(hour_s) == now.hour
        if not (minute_ok and hour_ok):
            return False
        return _stale(last_at, now)
    except (ValueError, TypeError):
        return _stale(last_at, now)


def _stale(last_at: Any, now: datetime) -> bool:
    if last_at is None:
        return True
    if isinstance(last_at, str):
        try:
            last_at = datetime.fromisoformat(last_at)
        except ValueError:
            return True
    if last_at.tzinfo is None:
        last_at = last_at.replace(tzinfo=timezone.utc)
    return (now - last_at) > timedelta(hours=20)


def _has_pending_run(session: Any, project_id: UUID) -> bool:
    from sqlalchemy import text

    try:
        row = session.execute(
            text(
                "SELECT 1 FROM analysis_runs WHERE project_id = :pid "
                "AND status IN ('queued', 'running') LIMIT 1"
            ),
            {"pid": str(project_id)},
        ).first()
        return row is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Gemini score_fn wiring (Track 3 → Track 2, lazy imports only)
# ---------------------------------------------------------------------------


def is_gemini_enabled() -> bool:
    """True when a non-placeholder GEMINI_API_KEY is configured.

    Lazy Track 2 import keeps the worker import-safe offline. Never logs or
    returns the key itself — boolean only.
    """
    try:
        from app.agents.base import is_gemini_configured  # type: ignore
    except Exception:
        return False
    try:
        return bool(is_gemini_configured())
    except Exception:
        return False


def _coerce_json_list(value: Any) -> list[Any]:
    """Best-effort JSON list coercion (Postgres JSONB vs SQLite TEXT)."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            import json as _json

            parsed = _json.loads(text)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _proposal_to_pipeline_dict(
    proposal: Any, criteria_by_code: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Convert one Track 2 proposal (model or dict) to pipeline shape.

    Pipeline shape (see ``stub_score_proposals``): ``criterion_code``,
    ``max_points``, ``ai_proposed_points`` (clamped to ``[0, max_points]``),
    ``ai_reasoning``, ``ai_confidence`` (clamped to ``[0, 1]``),
    ``score_state`` (``estimated``/``verified``/``needs_review``),
    ``missing_for_next_level``, ``evidence_paths``. Never carries
    ``human_override_*``.
    """
    if hasattr(proposal, "model_dump"):
        try:
            data = dict(proposal.model_dump())
        except Exception:
            data = {}
    elif isinstance(proposal, dict):
        data = dict(proposal)
    else:
        data = {}
    code = str(
        data.get("criterion_code", data.get("code", "unknown")) or "unknown"
    )
    fallback_max = int(criteria_by_code.get(code, {}).get("max_points", 0) or 0)
    try:
        max_pts = int(data.get("max_points", fallback_max) or fallback_max or 0)
    except (TypeError, ValueError):
        max_pts = fallback_max
    try:
        proposed = int(data.get("ai_proposed_points", 0) or 0)
    except (TypeError, ValueError):
        proposed = 0
    if max_pts > 0:
        proposed = max(0, min(proposed, max_pts))
    else:
        proposed = max(0, proposed)
    state = data.get("score_state", "needs_review")
    state = getattr(state, "value", state)
    state = str(state or "needs_review").lower()
    if state not in ("estimated", "verified", "needs_review"):
        state = "needs_review"
    try:
        confidence = float(data.get("ai_confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))
    paths = data.get("cited_evidence_paths", data.get("evidence_paths", []))
    if not isinstance(paths, list):
        paths = _coerce_json_list(paths)
    return {
        "criterion_code": code,
        "max_points": max_pts,
        "ai_proposed_points": proposed,
        "ai_reasoning": str(data.get("ai_reasoning", "") or ""),
        "ai_confidence": confidence,
        "score_state": state,
        "missing_for_next_level": data.get("missing_for_next_level"),
        "evidence_paths": [str(p) for p in paths[:5]],
    }


def build_gemini_score_fn() -> Callable[..., list[dict[str, Any]]]:
    """Build a pipeline ``score_fn`` delegating to Track 2 Rubric Analyst.

    The returned callable has signature ``(criteria, evidence) -> proposals``
    matching :func:`analysis_pipeline.stub_score_proposals`. Track 2 imports
    happen lazily inside the wrapper so module import never requires a key,
    the SDK, or the network. Any exception (including
    ``GeminiUnavailableError``) falls back to the deterministic stub and logs
    a WARNING with the error class name only.
    """

    def _gemini_score_fn(
        criteria: Any, evidence: Any
    ) -> list[dict[str, Any]]:
        try:
            from app.agents import rubric_analyst  # type: ignore  # lazy Track 2
        except Exception as exc:
            logger.warning(
                "Gemini scoring unavailable, using stub (%s).",
                type(exc).__name__,
            )
            from app.services.analysis_pipeline import stub_score_proposals

            return stub_score_proposals(criteria, evidence)
        try:
            output = rubric_analyst.evaluate_scorecard(
                criteria=criteria,
                evidence_items=list(evidence or []),
            )
            proposals = getattr(output, "criteria_evaluations", None)
            if proposals is None:
                raise ValueError("Track 2 scorecard missing criteria_evaluations")
            by_code = {
                str(c.get("code")): c
                for c in (criteria or [])
                if isinstance(c, dict) and c.get("code")
            }
            converted = [
                _proposal_to_pipeline_dict(p, by_code) for p in proposals
            ]
            if not converted:
                raise ValueError("Track 2 scorecard returned no proposals")
            return converted
        except Exception as exc:
            logger.warning(
                "Gemini scoring fallback to stub (%s).", type(exc).__name__
            )
            from app.services.analysis_pipeline import stub_score_proposals

            return stub_score_proposals(criteria, evidence)

    return _gemini_score_fn


# ---------------------------------------------------------------------------
# Run execution
# ---------------------------------------------------------------------------

def process_single_run(
    session: Any,
    run_id: UUID,
    *,
    notify_subject: str = "DevTrack AI analysis complete",
) -> bool:
    """Execute one claimed run end-to-end. Returns True on completion.

    Steps: load run+project → pipeline stages → persist snapshot →
    mark completed/failed → send+purge ephemeral notification.
    """
    from app.services.analysis_pipeline import persist_pipeline_result, run_analysis_stages
    from app.services.notification_service import EPHEMERAL_NOTIFICATIONS, send_and_purge

    run = _get_run(session, run_id)
    if run is None:
        return False
    project = _get_project(session, getattr(run, "project_id"))
    previous_sha = getattr(run, "previous_commit_sha", None)
    gemini_enabled = is_gemini_enabled()
    # Boolean only — never log the key itself.
    logger.info(
        "worker scoring path gemini_enabled=%s run_id=%s",
        "true" if gemini_enabled else "false",
        run_id,
    )
    score_fn = build_gemini_score_fn() if gemini_enabled else None
    try:
        result = run_analysis_stages(
            github_repo_url=getattr(project, "github_repo_url", ""),
            diary_override=getattr(project, "diary_path", None),
            deployment_override=getattr(project, "deployment_url", None),
            dev_statuses=_dev_statuses(session, getattr(run, "project_id")),
            criteria=_project_criteria(session, project),
            previous_commit_sha=previous_sha,
            score_fn=score_fn,
        )
        persist_pipeline_result(
            session, analysis_run_id=run_id, project_id=getattr(run, "project_id"), result=result
        )
        run.status = _analysis_status("completed")
        run.completed_at = _utcnow()
        if project is not None:
            project.last_analysis_at = _utcnow()
        session.commit()
        ok = True
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            pass
        run = _get_run(session, run_id)
        if run is not None:
            run.status = _analysis_status("failed")
            run.error_message = f"{type(exc).__name__}: {str(exc)[:500]}"
            run.completed_at = _utcnow()
            try:
                session.commit()
            except Exception:
                session.rollback()
        logger.warning("Analysis run failed (%s).", type(exc).__name__)
        ok = False
    try:
        from app.core.telemetry import record_analysis_run_outcome, start_correlated_span

        with start_correlated_span(
            "worker.process_single_run",
            attributes={"analysis_run.id": str(run_id), "analysis_run.ok": str(ok)},
        ) as trace_id:
            record_analysis_run_outcome(ok)
            logger.info(
                "worker_run_finished analysis_run_id=%s status=%s trace_id=%s",
                run_id,
                "completed" if ok else "failed",
                trace_id,
            )
    except Exception:
        pass
    # Ephemeral notification: purged on success AND failure; never logged.
    # Missing entry (no address queued via queue_notification) is a safe no-op.
    try:
        body = (
            f"Your DevTrack AI analysis finished with status "
            f"{'completed' if ok else 'failed'}."
        )
        notified = send_and_purge(run_id, notify_subject, body, registry=EPHEMERAL_NOTIFICATIONS)
        if notified:
            logger.info("Ephemeral notification dispatched for run %s.", run_id)
        else:
            # No-op: nothing was queued — log only the run id, never an address.
            logger.info("No ephemeral notification queued for run %s.", run_id)
    except Exception as exc:
        # Never log the address; run id only.
        logger.warning(
            "Ephemeral notification error (%s) for run %s.", type(exc).__name__, run_id
        )
    _ = notify_subject  # subject is caller-configurable only
    return ok


def _dev_statuses(session: Any, project_id: Any) -> list[str]:
    from sqlalchemy import text

    try:
        rows = session.execute(
            text("SELECT status FROM development_milestones WHERE project_id = :pid"),
            {"pid": str(project_id)},
        ).all()
        return [str(r[0]) for r in rows]
    except Exception:
        return []


def _project_criteria(session: Any, project: Any) -> list[dict[str, Any]]:
    """Load rubric criteria dicts for the scorer (enriched for Track 2).

    Returns ``{code, name, description, display_order, max_points,
    scoring_levels, required_evidence_types}`` dicts so the Gemini Rubric
    Analyst can evaluate against exact official scoring levels. Falls back
    to minimal ``{code, max_points}`` dicts (stub-compatible) when the
    enriched query fails. Handles Postgres JSONB and SQLite TEXT storage.
    """
    if project is None:
        return []
    from sqlalchemy import text

    try:
        rubric_id = getattr(project, "rubric_id")
        rows = session.execute(
            text(
                "SELECT code, name, description, display_order, max_points, "
                "scoring_levels, required_evidence_types "
                "FROM rubric_criteria "
                "WHERE rubric_id = :rid ORDER BY display_order"
            ),
            {"rid": str(rubric_id)},
        ).all()
        enriched: list[dict[str, Any]] = []
        for row in rows:
            try:
                (
                    code,
                    name,
                    description,
                    display_order,
                    max_pts,
                    scoring_levels,
                    required_types,
                ) = tuple(row)[:7]
            except (TypeError, ValueError):
                continue
            enriched.append(
                {
                    "code": str(code),
                    "name": str(name or code),
                    "description": str(description or ""),
                    "display_order": int(display_order or 0),
                    "max_points": int(max_pts or 0),
                    "scoring_levels": _coerce_json_list(scoring_levels),
                    "required_evidence_types": _coerce_json_list(required_types),
                }
            )
        if enriched:
            return enriched
    except Exception:
        pass
    # Minimal fallback (stub-compatible): code + max_points only.
    try:
        rubric_id = getattr(project, "rubric_id")
        rows = session.execute(
            text(
                "SELECT code, max_points FROM rubric_criteria "
                "WHERE rubric_id = :rid ORDER BY display_order"
            ),
            {"rid": str(rubric_id)},
        ).all()
        return [{"code": str(code), "max_points": int(max_pts)} for code, max_pts in rows]
    except Exception:
        return []


def _get_run(session: Any, run_id: UUID) -> Any | None:
    try:
        from app.models.models import AnalysisRun  # type: ignore  # read-only

        return session.get(AnalysisRun, run_id)
    except Exception:
        from sqlalchemy import text

        try:
            return session.execute(
                text("SELECT * FROM analysis_runs WHERE id = :rid"), {"rid": str(run_id)}
            ).first()
        except Exception:
            return None


def _get_project(session: Any, project_id: Any) -> Any | None:
    try:
        from app.models.models import Project  # type: ignore  # read-only

        return session.get(Project, project_id)
    except Exception:
        return None


def _analysis_status(value: str) -> Any:
    try:
        from app.schemas.enums import AnalysisStatus  # type: ignore

        return AnalysisStatus(value)
    except Exception:
        return value


# ---------------------------------------------------------------------------
# Loop entry points
# ---------------------------------------------------------------------------

SessionFactory = Callable[[], Any]


def run_once(session_factory: SessionFactory) -> dict[str, int]:
    """Claim and process a single queued run (plus daily scheduling)."""
    stats = {"scheduled": 0, "processed": 0, "completed": 0, "failed": 0}
    with session_factory() as session:
        try:
            stats["scheduled"] = schedule_daily_analyses(session)
        except Exception:
            pass
    with session_factory() as session:
        try:
            run_id = claim_next_queued_run(session)
            session.commit()
        except Exception:
            session.rollback()
            return stats
        if run_id is None:
            return stats
        stats["processed"] = 1
    with session_factory() as session:
        ok = process_single_run(session, run_id)
        stats["completed" if ok else "failed"] = 1
    return stats


def run_forever(
    session_factory: SessionFactory,
    *,
    poll_interval_seconds: int | None = None,
    stop_after: int | None = None,
) -> None:
    """Poll forever (worker daemon). ``stop_after`` caps iterations (tests)."""
    interval = poll_interval_seconds or int(
        os.environ.get("WORKER_POLL_INTERVAL_SECONDS", "5")
    )
    iterations = 0
    while True:
        try:
            run_once(session_factory)
        except Exception as exc:
            logger.warning("Worker iteration failed (%s).", type(exc).__name__)
            time.sleep(min(interval, 5))
            continue
        iterations += 1
        if stop_after is not None and iterations >= stop_after:
            return
        time.sleep(max(interval, 1))


if __name__ == "__main__":  # pragma: no cover - daemon entry
    # Runtime wiring only (kept out of module scope so unit tests and Track 1
    # imports never require a configured DB session factory).
    logging.basicConfig(level=logging.INFO)
    try:
        from app.db.session import SessionLocal  # type: ignore  # Track 1-owned
    except Exception as exc:
        raise SystemExit(f"Worker needs app.db.session.SessionLocal: {exc}")
    logger.info("DevTrack AI worker starting.")
    run_forever(SessionLocal)
