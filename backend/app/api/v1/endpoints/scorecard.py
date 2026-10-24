"""Scorecard + human override endpoints.

- effective_points = human_override_points if set else ai_proposed_points.
- PATCH preserves ai_proposed_points/ai_reasoning untouched; only sets
  human_override_points, human_override_reason, score_state, overridden_at.
- Advisory disclaimer banner is always present (never an official grade).
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.helpers import build_expected_score, get_project_or_404, latest_run
from app.core.deps import get_current_user, get_db
from app.models.models import AnalysisRun, CriterionAssessment, EvidenceItem, Rubric
from app.schemas.api_contracts import (
    CriterionAssessmentSchema,
    EvidenceItemSchema,
    ScorecardResponse,
    ScoreOverrideRequest,
    UserProfileSchema,
)
from app.schemas.enums import ScoreState

router = APIRouter(tags=["scorecard"])


def _criterion_to_schema(
    db: Session, a: CriterionAssessment
) -> CriterionAssessmentSchema:
    evidence: list[EvidenceItemSchema] = []
    if a.evidence_ids:
        try:
            wanted = {str(x) for x in a.evidence_ids}
        except TypeError:
            wanted = set()
        for e in (
            db.query(EvidenceItem)
            .filter(
                EvidenceItem.analysis_run_id == a.analysis_run_id,
                EvidenceItem.project_id == a.project_id,
            )
            .all()
        ):
            if str(e.id) in wanted:
                evidence.append(
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
                )
    crit = a.assessment_milestone.rubric_criterion if a.assessment_milestone else None
    return CriterionAssessmentSchema(
        id=a.id,
        analysis_run_id=a.analysis_run_id,
        project_id=a.project_id,
        assessment_milestone_id=a.assessment_milestone_id,
        criterion_code=a.criterion_code,
        criterion_name=crit.name if crit else "",
        scoring_levels=list(crit.scoring_levels) if crit else [],
        max_points=a.max_points,
        ai_proposed_points=a.ai_proposed_points,
        ai_reasoning=a.ai_reasoning,
        ai_confidence=a.ai_confidence,
        missing_for_next_level=a.missing_for_next_level,
        score_state=a.score_state,
        human_override_points=a.human_override_points,
        human_override_reason=a.human_override_reason,
        overridden_at=a.overridden_at,
        effective_points=a.effective_points,
        evidence_items=evidence,
    )


@router.get("/projects/{project_id}/scorecard", response_model=ScorecardResponse)
def get_scorecard(
    project_id: UUID,
    analysis_run_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> ScorecardResponse:
    project = get_project_or_404(db, project_id)
    rubric = db.get(Rubric, project.rubric_id)
    run: AnalysisRun | None
    if analysis_run_id is not None:
        run = db.get(AnalysisRun, analysis_run_id)
        if run is None or run.project_id != project.id:
            raise HTTPException(status_code=404, detail="Analysis run not found")
    else:
        run = latest_run(db, project.id)
    assessments: list[CriterionAssessment] = []
    if run is not None:
        assessments = (
            db.query(CriterionAssessment)
            .filter(CriterionAssessment.analysis_run_id == run.id)
            .all()
        )
    expected = build_expected_score(db, project, run)
    return ScorecardResponse(
        project_id=project.id,
        analysis_run_id=run.id if run else None,
        commit_sha=run.commit_sha if run else None,
        rubric_title=rubric.title if rubric else project.course_name,
        rubric_version=rubric.version if rubric else "unknown",
        rubric_source_url=rubric.source_url if rubric else None,
        is_official_rubric=rubric.is_official if rubric else True,
        expected_score=expected,
        criteria_assessments=[_criterion_to_schema(db, a) for a in assessments],
    )


@router.patch(
    "/projects/{project_id}/scorecard/{criterion_assessment_id}",
    response_model=CriterionAssessmentSchema,
)
def override_score(
    project_id: UUID,
    criterion_assessment_id: UUID,
    body: ScoreOverrideRequest,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> CriterionAssessmentSchema:
    project = get_project_or_404(db, project_id)
    assessment = db.get(CriterionAssessment, criterion_assessment_id)
    if assessment is None or assessment.project_id != project.id:
        raise HTTPException(status_code=404, detail="Criterion assessment not found")
    if (
        body.human_override_points is not None
        and body.human_override_points > assessment.max_points
    ):
        raise HTTPException(
            status_code=400,
            detail=f"human_override_points exceeds max_points ({assessment.max_points})",
        )
    # Override preservation: ONLY these fields change. ai_proposed_points and
    # ai_reasoning stay stored for side-by-side comparison.
    if body.score_state not in (
        ScoreState.VERIFIED,
        ScoreState.NEEDS_REVIEW,
        ScoreState.ESTIMATED,
    ):
        raise HTTPException(status_code=400, detail="Invalid score_state")
    assessment.score_state = body.score_state
    assessment.human_override_points = body.human_override_points
    assessment.human_override_reason = body.human_override_reason
    assessment.overridden_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assessment)
    return _criterion_to_schema(db, assessment)
