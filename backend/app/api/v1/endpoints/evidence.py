"""GET /api/v1/projects/{id}/evidence — filterable evidence explorer."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.helpers import get_project_or_404
from app.core.deps import get_current_user, get_db
from app.models.models import EvidenceItem
from app.schemas.api_contracts import EvidenceItemSchema, UserProfileSchema
from app.schemas.enums import EvidenceType

router = APIRouter(tags=["evidence"])


@router.get("/projects/{project_id}/evidence", response_model=list[EvidenceItemSchema])
def list_evidence(
    project_id: UUID,
    evidence_type: EvidenceType | None = Query(default=None),
    analysis_run_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> list[EvidenceItemSchema]:
    project = get_project_or_404(db, project_id)
    q = db.query(EvidenceItem).filter(EvidenceItem.project_id == project.id)
    if evidence_type is not None:
        q = q.filter(EvidenceItem.evidence_type == evidence_type)
    if analysis_run_id is not None:
        q = q.filter(EvidenceItem.analysis_run_id == analysis_run_id)
    items = q.order_by(EvidenceItem.created_at.desc()).all()
    return [
        EvidenceItemSchema(
            id=e.id,
            analysis_run_id=e.analysis_run_id,
            project_id=e.project_id,
            evidence_type=e.evidence_type,
            title=e.title,
            path_or_url=e.path_or_url,
            commit_sha=e.commit_sha,
            snippet=e.snippet,
            metadata_json=e.metadata_json,
            created_at=e.created_at,
        )
        for e in items
    ]
