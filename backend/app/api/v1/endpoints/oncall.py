"""POST /api/v1/oncall/diagnose — bounded read-only on-call endpoint (Phase 4).

Resolves the agent through `Depends(get_oncall_agent)` (Protocol only —
never a Stub import): Track 2 overrides the getter with the real
read-only Prometheus/Loki/Tempo agent, while the default resolves to a
deterministic placeholder shaped as OnCallDiagnosisResponse.
No remediation is ever executed here — only proposed as text.
"""

from fastapi import APIRouter, Depends

from app.api.protocols import OnCallAgentProtocol, get_oncall_agent
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
    agent: OnCallAgentProtocol = Depends(get_oncall_agent),
) -> OnCallDiagnosisResponse:
    # Track 2 wires the real OnCallAgentProtocol.diagnose() backed by
    # read-only Prometheus/Loki/Tempo queries (see on-call-diagnostics skill)
    # via app.dependency_overrides[get_oncall_agent].
    result = agent.diagnose(
        body.alert_name, body.time_window_minutes, body.context_notes
    )
    return OnCallDiagnosisResponse(**result)
