"""Shared endpoint helpers: GitHub URL validation + summary builders.

Assessment vs Development separation: builders compute the two progress
dimensions independently — development completion from development_milestones
only; expected course score from criterion_assessments only.
"""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.models import (
    AnalysisRun,
    AssessmentMilestone,
    CriterionAssessment,
    DevelopmentMilestone,
    Project,
    Rubric,
)
from app.schemas.api_contracts import (
    DevelopmentProgressSummarySchema,
    ExpectedScoreSummarySchema,
)
from app.schemas.enums import DevelopmentMilestoneStatus, ScoreState

_GITHUB_RE = re.compile(
    r"^https://github\.com/([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+?)(?:\.git)?/?$"
)


def parse_github_url(url: str) -> tuple[str, str] | None:
    """Accept only public https://github.com/<owner>/<repo> URLs."""
    match = _GITHUB_RE.match(url.strip())
    if not match:
        return None
    owner, repo = match.group(1), match.group(2)
    if owner in ("", ".", "..") or repo in ("", ".", ".."):
        return None
    return owner, repo


def get_or_404(db: Session, model, obj_id: UUID, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def get_project_or_404(db: Session, project_id: UUID) -> Project:
    return get_or_404(db, Project, project_id, "Project")


def latest_run(db: Session, project_id: UUID) -> AnalysisRun | None:
    return (
        db.query(AnalysisRun)
        .filter(AnalysisRun.project_id == project_id)
        .order_by(AnalysisRun.created_at.desc())
        .first()
    )


def build_expected_score(
    db: Session, project: Project, run: AnalysisRun | None
) -> ExpectedScoreSummarySchema:
    """Expected course score from criterion_assessments ONLY.

    effective_points = human_override_points if set else ai_proposed_points.
    Verified tallies count score_state == verified AND human-overridden rows.
    """
    rubric = db.get(Rubric, project.rubric_id)
    max_points = rubric.max_points if rubric else 24
    passing = rubric.passing_threshold if rubric else 10
    summary = ExpectedScoreSummarySchema(max_points=max_points, passing_threshold=passing)
    if run is None:
        return summary
    assessments = (
        db.query(CriterionAssessment)
        .filter(CriterionAssessment.analysis_run_id == run.id)
        .all()
    )
    estimated = sum(a.effective_points for a in assessments)
    verified = sum(
        a.effective_points
        for a in assessments
        if a.score_state == ScoreState.VERIFIED and a.human_override_points is not None
    )
    potential = max(0, max_points - estimated)
    summary.estimated_points = estimated
    summary.verified_points = verified
    summary.effective_points = estimated
    summary.potential_additional_points = potential
    summary.meets_passing_threshold = (
        estimated >= passing if passing is not None else False
    )
    return summary


def build_development_progress(
    db: Session, project: Project
) -> DevelopmentProgressSummarySchema:
    """Development completion from development_milestones ONLY.

    Never reads or writes criterion_assessments (no auto-awarding).
    """
    tasks = (
        db.query(DevelopmentMilestone)
        .filter(DevelopmentMilestone.project_id == project.id)
        .all()
    )
    completed = sum(1 for t in tasks if t.status == DevelopmentMilestoneStatus.COMPLETED)
    partial = sum(1 for t in tasks if t.status == DevelopmentMilestoneStatus.PARTIAL)
    outstanding = len(tasks) - completed - partial
    pct = round(completed / len(tasks) * 100.0, 1) if tasks else 0.0
    return DevelopmentProgressSummarySchema(
        completed_tasks=completed,
        partial_tasks=partial,
        outstanding_tasks=len(tasks) - completed - partial if tasks else 0,
        total_tasks=len(tasks),
        completion_pct=pct,
        milestones_approved=project.milestones_approved,
    )


def assessment_with_code(
    db: Session, project_id: UUID
) -> list[tuple[AssessmentMilestone, str, str, list]]:
    """(assessment_milestone, criterion_code, criterion_name, scoring_levels)."""
    rows = (
        db.query(AssessmentMilestone)
        .filter(AssessmentMilestone.project_id == project_id)
        .order_by(AssessmentMilestone.display_order)
        .all()
    )
    out = []
    for am in rows:
        crit = am.rubric_criterion
        out.append(
            (
                am,
                crit.code if crit else "",
                crit.name if crit else am.title,
                list(crit.scoring_levels) if crit else [],
            )
        )
    return out
