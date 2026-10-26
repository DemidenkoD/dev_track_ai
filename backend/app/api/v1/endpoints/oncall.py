"""On-call endpoints (Phase 4 + 4b History tab).

- POST /api/v1/oncall/diagnose — bounded read-only diagnosis (JWT, unchanged).
- POST /api/v1/oncall/webhook — Alertmanager native webhook (shared secret,
  NO user JWT). Dedupes on fingerprint+startsAt, persists redacted payload +
  synchronous agent diagnosis, returns 202 with incident IDs.
- GET /api/v1/oncall/incidents — History list (JWT, ?status&?limit&?project_id).
- GET /api/v1/oncall/incidents/{id} — History detail with remediation plan (JWT).
- POST /api/v1/oncall/incidents/{id}/acknowledge — mark acknowledged + note (JWT).

Advisory read-only: remediation is stored/displayed as recommended_actions
text only and is NEVER executed here.
Zero persistent email storage: payloads are redacted of emails/JWTs/secrets
before persistence; no email column exists on oncall_incidents.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.protocols import OnCallAgentProtocol, get_oncall_agent
from app.core.config import get_settings
from app.core.deps import get_current_user, get_db
from app.models.models import OnCallIncident
from app.schemas.api_contracts import (
    AcknowledgeRequest,
    AlertmanagerWebhookPayload,
    OnCallDiagnoseRequest,
    OnCallDiagnosisResponse,
    OnCallIncidentDetailSchema,
    OnCallIncidentSchema,
    OnCallWebhookResponse,
    UserProfileSchema,
)
from app.schemas.enums import OnCallIncidentStatus

router = APIRouter(tags=["oncall"])

logger = logging.getLogger("devtrack.oncall")

# Known placeholder webhook secrets that must never authenticate (fail-closed).
_PLACEHOLDER_WEBHOOK_SECRETS: frozenset[str] = frozenset(
    {
        "change-me-alertmanager-secret",
        "changeme-dev-only",
    }
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/=]+", re.IGNORECASE)
_API_KEY_RE = re.compile(
    r"(?i)(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*['\"]?[^'\",\s}]+['\"]?"
)
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


def _redact_text(value: str) -> str:
    redacted = _EMAIL_RE.sub("[redacted-email]", value)
    redacted = _JWT_RE.sub("[redacted-jwt]", redacted)
    redacted = _BEARER_RE.sub(r"\1[redacted]", redacted)
    redacted = _API_KEY_RE.sub(r"\1=[redacted]", redacted)
    return redacted


def _redact_json(obj: Any) -> Any:
    if isinstance(obj, str):
        return _redact_text(obj)
    if isinstance(obj, list):
        return [_redact_json(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): _redact_json(v) for k, v in obj.items()}
    return obj


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _check_webhook_secret(
    authorization: str | None = None,
    x_alertmanager_secret: str | None = None,
) -> None:
    """Shared-secret gate for the Alertmanager webhook (no user JWT).

    Accepts `Authorization: Bearer <secret>` or the
    `X-Alertmanager-Secret` header. 401 otherwise. The secret value
    itself is never logged or echoed.
    """
    settings = get_settings()
    expected = (settings.ALERTMANAGER_WEBHOOK_SECRET or "").strip()
    if not expected or expected.lower() in _PLACEHOLDER_WEBHOOK_SECRETS:
        # Fail-closed: unconfigured or placeholder secret never authenticates.
        # No secret value is logged or echoed.
        logger.warning("webhook secret not configured, rejecting")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Alertmanager webhook secret",
        )
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    elif x_alertmanager_secret:
        provided = x_alertmanager_secret.strip()
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Alertmanager webhook secret",
        )


def _incident_to_list_schema(inc: OnCallIncident) -> OnCallIncidentSchema:
    return OnCallIncidentSchema(
        id=inc.id,
        alert_name=inc.alert_name,
        severity=inc.severity,
        service=inc.service,
        status=inc.status,
        fingerprint=inc.fingerprint,
        starts_at=inc.starts_at,
        ends_at=inc.ends_at,
        confidence=inc.confidence,
        read_only_verified=inc.read_only_verified,
        acknowledge_note=inc.acknowledge_note,
        project_id=inc.project_id,
        created_at=inc.created_at,
        updated_at=inc.updated_at,
    )


def _incident_to_detail_schema(inc: OnCallIncident) -> OnCallIncidentDetailSchema:
    diagnosis_payload = inc.diagnosis_json or {}
    try:
        diagnosis = OnCallDiagnosisResponse(**diagnosis_payload)
    except Exception:
        diagnosis = OnCallDiagnosisResponse(
            incident_summary=str(diagnosis_payload.get("incident_summary", "")),
            root_cause_hypothesis=str(
                diagnosis_payload.get("root_cause_hypothesis", "")
            ),
            confidence=float(diagnosis_payload.get("confidence", 0.0) or 0.0),
            evidence_citations=list(
                diagnosis_payload.get("evidence_citations", []) or []
            ),
            recommended_actions=list(
                diagnosis_payload.get("recommended_actions", []) or []
            ),
            read_only_verified=bool(
                diagnosis_payload.get("read_only_verified", True)
            ),
        )
    return OnCallIncidentDetailSchema(
        **_incident_to_list_schema(inc).model_dump(),
        alert_payload_json=inc.alert_payload_json or {},
        diagnosis=diagnosis,
    )


def create_security_incident(
    db: Session,
    project_id: UUID,
    rule_id: str,
    severity: str,
    file_path: str | None,
    commit_sha: str,
    summary: str,
    remediation_hints: list[str] | None = None,
) -> OnCallIncident:
    """Track-1-owned creator linking critical/high scanner findings to History.

    Called by Track 3's ``_persist_security_report`` (which must import — not
    reimplement — this function). Signature is stable: do not rename params.

    Builds ``alert_name="SecurityCritical:{rule_id}"``,
    ``fingerprint=sha256(rule_id|file_path|commit_sha)hex[0:32]``,
    ``service="security-scanner"``, ``status=firing`` and a ``diagnosis_json``
    shaped like ``OnCallDiagnosisResponse`` (``confidence=0.75``,
    ``read_only_verified=True``; remediation stored as text only, never
    executed). Dedupes on ``fingerprint`` alone within the same
    ``project_id`` + ``commit_sha`` — returns the existing row instead of
    inserting a duplicate. ``starts_at`` is now UTC at creation time.
    Payloads are redacted of emails/JWTs/secrets before persistence; no email
    is ever stored (zero persistent email invariant).
    """
    normalized_severity = (severity or "unknown").strip().lower() or "unknown"
    if normalized_severity not in ("critical", "high"):
        normalized_severity = (severity or "unknown").strip() or "unknown"
    fingerprint = hashlib.sha256(
        f"{rule_id}|{file_path or ''}|{commit_sha}".encode("utf-8")
    ).hexdigest()[:32]
    alert_name = f"SecurityCritical:{rule_id}"
    hints = [str(h) for h in (remediation_hints or []) if str(h).strip()]

    existing = (
        db.query(OnCallIncident)
        .filter(
            OnCallIncident.fingerprint == fingerprint,
            OnCallIncident.project_id == project_id,
        )
        .all()
    )
    for row in existing:
        payload = row.alert_payload_json or {}
        if isinstance(payload, dict) and payload.get("commit_sha") == commit_sha:
            return row
    if existing and commit_sha:
        # Fallback: same fingerprint + project, payload redaction may differ;
        # treat fingerprint alone as the dedupe key per the bridge contract.
        for row in existing:
            payload = row.alert_payload_json or {}
            if not isinstance(payload, dict) or "commit_sha" not in payload:
                return row

    now = datetime.now(timezone.utc)
    redacted_summary = _redact_text(summary or "")
    redacted_hints = [_redact_text(h) for h in hints]
    redacted_path = _redact_text(file_path) if file_path else ""
    diagnosis = OnCallDiagnosisResponse(
        incident_summary=redacted_summary
        or f"Critical security finding '{rule_id}' detected by security scanner.",
        root_cause_hypothesis=(
            f"Scanner rule '{rule_id}' flagged "
            f"{redacted_path or 'repository content'} at commit {commit_sha}."
        ),
        confidence=0.75,
        evidence_citations=[
            {
                "source": "security-scanner",
                "query": rule_id,
                "excerpt": redacted_path,
            }
        ],
        recommended_actions=redacted_hints,
        read_only_verified=True,
    )
    redacted_payload = _redact_json(
        {
            "rule_id": rule_id,
            "severity": normalized_severity,
            "file_path": file_path,
            "commit_sha": commit_sha,
            "summary": summary,
        }
    )
    row = OnCallIncident(
        alert_name=alert_name,
        severity=normalized_severity,
        service="security-scanner",
        status=OnCallIncidentStatus.FIRING,
        fingerprint=fingerprint,
        starts_at=now,
        ends_at=None,
        alert_payload_json=redacted_payload,
        diagnosis_json=diagnosis.model_dump(mode="json"),
        confidence=float(diagnosis.confidence or 0.0),
        read_only_verified=True,
        project_id=project_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/oncall/diagnose", response_model=OnCallDiagnosisResponse)
def diagnose(
    body: OnCallDiagnoseRequest,
    _user: UserProfileSchema = Depends(get_current_user),
    agent: OnCallAgentProtocol = Depends(get_oncall_agent),
) -> OnCallDiagnosisResponse:
    # Track 2 wires the real OnCallAgentProtocol.diagnose() backed by
    # read-only Prometheus/Loki/Tempo queries (see on-call-diagnostics skill)
    # via app.dependency_overrides[get_oncall_agent].
    result = agent.diagnose(
        body.alert_name, body.time_window_minutes, body.context_notes
    )
    return OnCallDiagnosisResponse(**result)


@router.post(
    "/oncall/webhook",
    response_model=OnCallWebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def alertmanager_webhook(
    body: AlertmanagerWebhookPayload,
    db: Session = Depends(get_db),
    agent: OnCallAgentProtocol = Depends(get_oncall_agent),
    authorization: str | None = Header(default=None),
    x_alertmanager_secret: str | None = Header(default=None),
) -> OnCallWebhookResponse:
    _check_webhook_secret(authorization, x_alertmanager_secret)
    incidents: list[OnCallIncidentSchema] = []
    for alert in body.alerts:
        alert_name = (alert.labels.alertname or "unknown").strip() or "unknown"
        severity = (alert.labels.severity or "unknown").strip() or "unknown"
        service = (alert.labels.service or "unknown").strip() or "unknown"
        incoming_status = (alert.status or "firing").strip().lower()
        target_status = (
            OnCallIncidentStatus.RESOLVED
            if incoming_status == "resolved"
            else OnCallIncidentStatus.FIRING
        )
        starts_at = _as_utc(alert.startsAt) or datetime.now(timezone.utc)
        ends_at = _as_utc(alert.endsAt)

        # Dedupe on fingerprint+startsAt (timestamps compared in UTC so
        # SQLite naive vs aware storage never creates duplicates).
        existing: OnCallIncident | None = None
        for row in (
            db.query(OnCallIncident)
            .filter(OnCallIncident.fingerprint == alert.fingerprint)
            .all()
        ):
            row_starts = _as_utc(row.starts_at)
            if row_starts is not None and abs(
                (row_starts - starts_at).total_seconds()
            ) < 1.0:
                existing = row
                break

        redacted_payload = _redact_json(alert.model_dump(mode="json"))

        if existing is not None:
            existing.status = target_status
            if ends_at is not None:
                existing.ends_at = ends_at
            existing.alert_payload_json = redacted_payload
            existing.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(existing)
            incidents.append(_incident_to_list_schema(existing))
            continue

        summary = (
            (alert.annotations.summary or "").strip()
            or (alert.annotations.description or "").strip()
        )
        context_notes = f"[{severity}/{service}] {summary}".strip()
        try:
            raw_diagnosis = agent.diagnose(alert_name, 30, context_notes or None)
            diagnosis = OnCallDiagnosisResponse(**raw_diagnosis)
        except Exception:
            diagnosis = OnCallDiagnosisResponse(
                incident_summary=(
                    f"Received alert '{alert_name}' [{severity}/{service}]. "
                    "Automated read-only triage is not wired yet."
                ),
                root_cause_hypothesis="No telemetry inspected yet — on-call agent stub.",
                confidence=0.0,
                evidence_citations=[],
                recommended_actions=[
                    "Check worker analysis job status and DB pool metrics manually.",
                ],
                read_only_verified=True,
            )
        row = OnCallIncident(
            alert_name=alert_name,
            severity=severity,
            service=service,
            status=target_status,
            fingerprint=alert.fingerprint,
            starts_at=starts_at,
            ends_at=ends_at,
            alert_payload_json=redacted_payload,
            diagnosis_json=diagnosis.model_dump(mode="json"),
            confidence=float(diagnosis.confidence or 0.0),
            read_only_verified=bool(diagnosis.read_only_verified),
            project_id=None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        incidents.append(_incident_to_list_schema(row))
    return OnCallWebhookResponse(incidents=incidents)


@router.get("/oncall/incidents", response_model=list[OnCallIncidentSchema])
def list_incidents(
    incident_status: OnCallIncidentStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    project_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> list[OnCallIncidentSchema]:
    query = db.query(OnCallIncident)
    if incident_status is not None:
        query = query.filter(OnCallIncident.status == incident_status)
    if project_id is not None:
        query = query.filter(OnCallIncident.project_id == project_id)
    rows = (
        query.order_by(OnCallIncident.starts_at.desc()).limit(limit).all()
    )
    return [_incident_to_list_schema(r) for r in rows]


@router.get(
    "/oncall/incidents/{incident_id}", response_model=OnCallIncidentDetailSchema
)
def get_incident(
    incident_id: UUID,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> OnCallIncidentDetailSchema:
    row = db.get(OnCallIncident, incident_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _incident_to_detail_schema(row)


@router.post(
    "/oncall/incidents/{incident_id}/acknowledge",
    response_model=OnCallIncidentDetailSchema,
)
def acknowledge_incident(
    incident_id: UUID,
    body: AcknowledgeRequest,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> OnCallIncidentDetailSchema:
    row = db.get(OnCallIncident, incident_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    row.status = OnCallIncidentStatus.ACKNOWLEDGED
    if body.note is not None:
        row.acknowledge_note = body.note.strip() or None
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _incident_to_detail_schema(row)
