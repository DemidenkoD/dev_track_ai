"""Ephemeral one-time email notification dispatcher (Track 3).

Zero-persistent-email invariant (backend/AGENTS.md §2.2):
    - No email column exists on any SQLAlchemy model — and this module adds none.
    - The recipient address lives ONLY in the in-memory
      :data:`EPHEMERAL_NOTIFICATIONS` registry keyed by ``analysis_run_id``.
    - The address is ``pop()``-ed (purged) immediately upon success OR failure.
    - The address is never written to logs, OpenTelemetry spans, or the DB.

Public API:
    - :class:`EphemeralNotificationRegistry` (``set`` / ``pop_once``)
    - :data:`EPHEMERAL_NOTIFICATIONS` (process-wide singleton)
    - :func:`queue_notification`
    - :func:`send_and_purge`
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
    """Volatile ``dict[UUID, str]`` holding one-time notification recipients."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[UUID, str] = {}

    def set(self, analysis_run_id: UUID, email: str) -> None:
        """Stage a one-time recipient address in volatile RAM only."""
        if not isinstance(analysis_run_id, UUID):
            analysis_run_id = UUID(str(analysis_run_id))
        if not _EMAIL_RE.match(email.strip()):
            raise ValueError("Invalid one-time notification email address.")
        with self._lock:
            self._store[analysis_run_id] = email.strip()

    def pop_once(self, analysis_run_id: UUID) -> str | None:
        """Atomically retrieve AND purge the staged address (single use)."""
        if not isinstance(analysis_run_id, UUID):
            analysis_run_id = UUID(str(analysis_run_id))
        with self._lock:
            return self._store.pop(analysis_run_id, None)

    def has(self, analysis_run_id: UUID) -> bool:
        if not isinstance(analysis_run_id, UUID):
            analysis_run_id = UUID(str(analysis_run_id))
        with self._lock:
            return analysis_run_id in self._store

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


#: Process-wide singleton. The API layer stages addresses here on
#: ``POST /analyses``; the worker purges them via :func:`send_and_purge`.
EPHEMERAL_NOTIFICATIONS = EphemeralNotificationRegistry()


def queue_notification(
    analysis_run_id: UUID, email: str | None, *, acknowledged: bool
) -> bool:
    """Stage a one-time notification address (API-layer entry point).

    Args:
        analysis_run_id: Queue record the address belongs to.
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
    logger.info("Ephemeral notification staged.")
    return True


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
    analysis_run_id: UUID,
    subject: str,
    body_text: str,
    *,
    registry: EphemeralNotificationRegistry | None = None,
) -> bool:
    """Send the completion email to the staged address, then purge it.

    The address is popped BEFORE sending so it is purged on success AND on
    failure. The address value never appears in logs, exceptions, or traces —
    only the boolean outcome and the run id are recorded.

    Args:
        analysis_run_id: Queue record whose staged address to consume.
        subject: Email subject line.
        body_text: Plain-text body.
        registry: Registry to use (defaults to the process singleton).

    Returns:
        True if an email was sent; False if none was staged or sending failed.
    Note: uses ``is not None`` (never ``or``) because an empty registry is
    falsy via ``__len__`` and must still be honored when passed explicitly.
    """
    reg = registry if registry is not None else EPHEMERAL_NOTIFICATIONS
    recipient = reg.pop_once(analysis_run_id)  # purge-first: single use
    if not recipient:
        return False
    cfg = _smtp_settings()
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
        logger.info("Ephemeral notification sent.")
        return True
    except Exception as exc:
        # Log only the failure class — never the recipient address.
        logger.warning("Ephemeral notification failed (%s).", type(exc).__name__)
        return False
