"""POST /api/v1/oncall/diagnose — bounded read-only on-call stub (Phase 4).

Track 1 returns a deterministic, explicitly read-only placeholder shaped as
OnCallDiagnosisResponse. Track 2 wires the real OnCallAgentProtocol
implementation (Prometheus/Loki/Tempo, read-only) via dependency override.
No remediation is ever executed here — only proposed as text.
"""

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.schemas.api_contracts import (
    OnCallDiagnoseRequest,
    OnCallDiagnosisResponse,
    UserProfileSchema,
)

router = APIRouter(tags=["oncall"])


@router.post("/oncall/diagnose", response_model=OnCallDiagnosisResponse)
def diagnose(
    body: OnCallDiagnoseRequest,
    _user: UserProfileSchema = Depends(get_current_user),
) -> OnCallDiagnosisResponse:
    # TODO(Track 2): override with OnCallAgentProtocol.diagnose() backed by
    # read-only Prometheus/Loki/Tempo queries (see on-call-diagnostics skill).
    return OnCallDiagnosisResponse(
        incident_summary=(
            f"Received alert '{body.alert_name}' "
            f"(window: last {body.time_window_minutes} minutes). "
            "Automated read-only triage is not wired yet (Track 2 TODO)."
        ),
        root_cause_hypothesis=(
            "No telemetry inspected yet — on-call agent stub. Context notes: "
            f"{body.context_notes or 'none provided'}."
        ),
        confidence=0.0,
        evidence_citations=[],
        recommended_actions=[
            "Wire the bounded read-only on-call agent (Track 2) for this alert.",
            "Check worker analysis job status and DB pool metrics manually.",
            "Consider raising ANALYSIS_TIMEOUT_SECONDS or enforcing shallow clones.",
        ],
        read_only_verified=True,
    )
