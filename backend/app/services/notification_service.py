"""Ephemeral one-time email notification dispatcher (Track 3).

Zero-persistent-email invariant (backend/AGENTS.md §2.2):
    - No email column exists on any SQLAlchemy model — and this module adds none.
    - The recipient address lives ONLY in the in-memory
      :data:`EPHEMERAL_NOTIFICATIONS` registry keyed by ``analysis_run_id``.
    - The address is ``pop()``-ed (purged) immediately upon success OR failure.
    - The address is never written to logs, OpenTelemetry spans, or the DB.

Option A same-process delivery contract (overseer lock):
    - The API process queues ``notify_email_once`` into
      :data:`EPHEMERAL_NOTIFICATIONS` via :func:`queue_notification`.
    - The worker (separate container/process) never sees that RAM, so the API
      process polls ``analysis_runs`` for completion and then calls
      :func:`build_completion_subject_and_body` + :func:`send_and_purge` in
      the SAME process memory.
    - Track 1 imports exactly ``build_completion_subject_and_body`` and
      ``send_and_purge`` for this; the worker fallback stays a harmless
      pop-once no-op (double-send impossible because ``pop_once`` purges).

Public API:
    - :class:`EphemeralNotificationRegistry` (``set`` / ``pop_once`` / ``clear``)
    - :data:`EPHEMERAL_NOTIFICATIONS` (process-wide singleton)
    - :func:`queue_notification`
    - :func:`build_completion_subject_and_body` (pure Option A builder)
    - :func:`send_and_purge` (bool wrapper, contract-invariant compatible)
    - :class:`NotifyOutcome` + :func:`send_and_purge_detailed` (richer status)
"""

from __future__ import annotations

import logging
import os
import re
import smtplib
import sys
import threading
from email.message import EmailMessage
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

logger = logging.getLogger(__name__)

#: Minimal email sanity check (full RFC validation happens at SMTP time).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SMTP_TIMEOUT_SECONDS = 15


class EphemeralNotificationRegistry:
    """Volatile ``dict[UUID, str]`` holding one-time notification recipients.

    Keys accept ``str | UUID`` (normalized to :class:`UUID`). The Track 1 API
    layer must call :func:`queue_notification` to stage an address; the Track 3
    worker consumes it via :meth:`pop_once` / :meth:`consume_or_none` or
    :func:`send_and_purge` (purge-before-send, single use).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[UUID, str] = {}

    @staticmethod
    def _normalize_key(analysis_run_id: UUID | str) -> UUID:
        if isinstance(analysis_run_id, UUID):
            return analysis_run_id
        return UUID(str(analysis_run_id))

    def set(self, analysis_run_id: UUID | str, email: str) -> None:
        """Stage a one-time recipient address in volatile RAM only."""
        analysis_run_id = self._normalize_key(analysis_run_id)
        if not _EMAIL_RE.match(email.strip()):
            raise ValueError("Invalid one-time notification email address.")
        with self._lock:
            self._store[analysis_run_id] = email.strip()

    def pop_once(self, analysis_run_id: UUID | str) -> str | None:
        """Atomically retrieve AND purge the staged address (single use)."""
        analysis_run_id = self._normalize_key(analysis_run_id)
        with self._lock:
            return self._store.pop(analysis_run_id, None)

    def consume_or_none(self, analysis_run_id: UUID | str) -> str | None:
        """Worker-facing alias for :meth:`pop_once` (missing entry → None)."""
        return self.pop_once(analysis_run_id)

    def has(self, analysis_run_id: UUID | str) -> bool:
        if isinstance(analysis_run_id, UUID):
            key = analysis_run_id
        else:
            try:
                key = UUID(str(analysis_run_id))
            except ValueError:
                return False
        with self._lock:
            return key in self._store

    def clear(self) -> None:
        """Remove all staged addresses (test isolation only).

        The QA track calls ``EPHEMERAL_NOTIFICATIONS.clear()`` in fixtures;
        without this method that call raised ``AttributeError`` (silently
        swallowed by ``except Exception`` in test setup), leaving state to
        leak between tests. Clears volatile RAM only — never touches DB/logs.
        """
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


#: Process-wide singleton. The API layer stages addresses here on
#: ``POST /analyses``; the worker purges them via :func:`send_and_purge`.
EPHEMERAL_NOTIFICATIONS = EphemeralNotificationRegistry()


def queue_notification(
    analysis_run_id: UUID | str, email: str | None, *, acknowledged: bool
) -> bool:
    """Stage a one-time notification address (API-layer entry point).

    The Track 1 API (``POST /analyses``) must call this function to stage
    ``notify_email_once``; the Track 3 worker later consumes it via
    :func:`send_and_purge` (which uses ``pop_once``/``consume_or_none``).
    The worker no-ops safely when nothing was staged.

    Args:
        analysis_run_id: Queue record the address belongs to (``str|UUID``).
        email: Optional ``notify_email_once`` value (None = no notification).
        acknowledged: Must be True (mirrors ``acknowledge_ephemeral_email``).

    Returns:
        True when an address was staged, False when no email was given.
    """
    if email is None or not str(email).strip():
        return False
    if not acknowledged:
        raise ValueError(
            "One-time email requires acknowledge_ephemeral_email=true."
        )
    EPHEMERAL_NOTIFICATIONS.set(analysis_run_id, str(email))
    # Deliberately log only the run id — never the address.
    logger.info("Ephemeral notification staged for run %s.", analysis_run_id)
    return True


def build_completion_subject_and_body(
    status: str, project_name: str = "DevTrack AI"
) -> tuple[str, str]:
    """Build the one-time completion subject/body (Option A, pure helper).

    Same-process contract: Track 1 polls ``analysis_runs`` for completion in
    the API process, then calls this builder + :func:`send_and_purge` with the
    SAME in-memory :data:`EPHEMERAL_NOTIFICATIONS` registry. The worker
    fallback is a harmless pop-once no-op, so double-send is impossible.

    Pure by design: no DB, no I/O, no logging, and deliberately NO email
    address parameter (the address stays only in the volatile registry and is
    never interpolated from logs/traces). Sync and fully typed.
    """
    normalized = (status or "").strip().lower() or "completed"
    project = (project_name or "").strip() or "DevTrack AI"
    subject = f"{project} analysis {normalized}"
    body = (
        f"Your {project} analysis run finished with status: {normalized}.\n"
        "View your scorecard and recommendations in the DevTrack AI UI.\n"
        "AI estimates are advisory and never official course grades."
    )
    return subject, body


def _smtp_settings() -> dict[str, object]:
    try:
        from app.core.config import get_settings  # type: ignore

        settings = get_settings()
        return {
            "host": settings.MAIL_SMTP_HOST,
            "port": settings.MAIL_SMTP_PORT,
            "secure": settings.MAIL_SMTP_SECURE,
            "user": settings.MAIL_SMTP_USER,
            "password": settings.MAIL_SMTP_PASS,
            "from": settings.MAIL_FROM,
        }
    except Exception:
        return {
            "host": os.environ.get("MAIL_SMTP_HOST", "smtp.example.com"),
            "port": int(os.environ.get("MAIL_SMTP_PORT", "465")),
            "secure": os.environ.get("MAIL_SMTP_SECURE", "true").lower() == "true",
            "user": os.environ.get("MAIL_SMTP_USER", ""),
            "password": os.environ.get("MAIL_SMTP_PASS", ""),
            "from": os.environ.get("MAIL_FROM", "DevTrack AI <user@example.com>"),
        }


def send_and_purge(
    analysis_run_id: UUID | str,
    subject: str,
    body_text: str,
    *,
    registry: EphemeralNotificationRegistry | None = None,
) -> bool:
    """Send the completion email to the staged address, then purge it.

    The address is popped BEFORE sending so it is purged on success AND on
    failure (including :class:`smtplib.SMTPException`). The address value
    never appears in logs, exceptions, or traces — only the boolean outcome,
    the run id, the exception class name, and the (non-secret) SMTP host are
    recorded. See :func:`send_and_purge_detailed` for the richer status form;
    this wrapper preserves the historical ``True``/``False`` singleton
    contract relied on by contract-invariant tests.

    Missing entry (nothing queued) is a safe no-op returning False. Note that
    the registry is process-local RAM: when the API (``uvicorn``, possibly
    ``--workers 2``) and the worker (``python -m app.worker.runner``) run in
    separate processes/containers, the worker's registry is empty by design
    and this no-op is expected. Email addresses must NEVER be stored in
    Postgres/Redis/logs/traces to bridge that gap (Zero Persistent Email
    invariant) — the cross-process handoff belongs to Track 1/6.

    Args:
        analysis_run_id: Queue record whose staged address to consume (str|UUID).
        subject: Email subject line.
        body_text: Plain-text body.
        registry: Registry to use (defaults to the process singleton).

    Returns:
        True if an email was sent; False if none was staged or sending failed.
    Note: uses ``is not None`` (never ``or``) because an empty registry is
    falsy via ``__len__`` and must still be honored when passed explicitly.
    """
    return send_and_purge_detailed(
        analysis_run_id, subject, body_text, registry=registry
    ).sent


class NotifyOutcome:
    """Richer notify status for the worker (volatile-only, no address stored).

    Attributes:
        sent: True only when SMTP accepted the message.
        queued: False when ``pop_once`` found nothing staged (safe no-op,
            typically because the API queued in a different process).
        smtp_host: Non-secret SMTP host used (for diagnostics only).
        error_type: Exception class name on failure, else None.
    """

    __slots__ = ("sent", "queued", "smtp_host", "error_type")

    def __init__(
        self, *, sent: bool, queued: bool, smtp_host: str, error_type: str | None
    ) -> None:
        self.sent = sent
        self.queued = queued
        self.smtp_host = smtp_host
        self.error_type = error_type

    def __bool__(self) -> bool:  # pragma: no cover - convenience only
        return self.sent


def send_and_purge_detailed(
    analysis_run_id: UUID | str,
    subject: str,
    body_text: str,
    *,
    registry: EphemeralNotificationRegistry | None = None,
) -> NotifyOutcome:
    """Purge-first send returning a :class:`NotifyOutcome`.

    Identical purge-first + volatile-only semantics to :func:`send_and_purge`
    (address is ``pop()``-ed before SMTP and never logged/persisted/traced),
    but the caller also learns whether an address was queued, which SMTP host
    was used, and the failure class on error — so the worker can record a
    ``notified`` counter/log without ever persisting the address.
    """
    reg = registry if registry is not None else EPHEMERAL_NOTIFICATIONS
    recipient = reg.pop_once(analysis_run_id)  # purge-first: single use
    cfg = _smtp_settings()
    smtp_host = str(cfg.get("host", "unknown"))
    if not recipient:
        # Expected whenever the API queued in a different process/container
        # (backend: uvicorn vs worker: python -m app.worker.runner, or prod
        # --workers 2): the worker's process-local registry is empty by
        # design. Deliberately NOT bridged via Postgres/Redis/logs/traces
        # (Zero Persistent Email invariant) — handoff belongs to Track 1/6.
        logger.warning(
            "No ephemeral notification queued for run %s - likely API/worker "
            "are separate processes (process-local registry); skipping.",
            analysis_run_id,
        )
        return NotifyOutcome(
            sent=False, queued=False, smtp_host=smtp_host, error_type=None
        )
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = str(cfg["from"])
    message["To"] = recipient
    message.set_content(body_text)
    try:
        host = str(cfg["host"])
        port = int(cfg["port"])  # type: ignore[arg-type]
        if bool(cfg["secure"]):
            with smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
                if cfg["user"]:
                    smtp.login(str(cfg["user"]), str(cfg["password"]))
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
                try:
                    smtp.starttls()
                except smtplib.SMTPException:
                    pass
                if cfg["user"]:
                    smtp.login(str(cfg["user"]), str(cfg["password"]))
                smtp.send_message(message)
        logger.info("Ephemeral notification sent for run %s.", analysis_run_id)
        return NotifyOutcome(
            sent=True, queued=True, smtp_host=smtp_host, error_type=None
        )
    except Exception as exc:
        # Structured warning: run id + exception type + non-secret host only.
        # Never the recipient address, user, or password.
        error_type = type(exc).__name__
        logger.warning(
            "Ephemeral notification failed error=%s host=%s for run %s.",
            error_type,
            smtp_host,
            analysis_run_id,
        )
        return NotifyOutcome(
            sent=False, queued=True, smtp_host=smtp_host, error_type=error_type
        )
