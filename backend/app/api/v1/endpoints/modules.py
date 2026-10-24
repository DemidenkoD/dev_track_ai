"""Recommendations / diary / security / deployments endpoints.

Read-only views over the latest Track 3 snapshots (404 when no snapshot
exists yet). POST deployments/check records via the DeploymentMonitorProtocol
stub — Track 1 performs NO raw httpx here (SSRF guard lives in Track 3's
deployment_monitor; see backend/AGENTS.md §2.3 and api/protocols.py TODO).
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session

from app.api.helpers import get_project_or_404, latest_run
from app.api.protocols import get_deployment_monitor
from app.core.deps import get_current_user, get_db
from app.models.models import (
    DeploymentCheck,
    DiarySnapshot,
    Recommendation,
    SecurityReport,
)
from app.schemas.api_contracts import (
    DeploymentCheckSchema,
    DeploymentCheckTriggerRequest,
    DiarySnapshotSchema,
    RecommendationSchema,
    SecurityFindingSchema,
    SecurityReportSchema,
    UserProfileSchema,
)
from app.schemas.enums import DeploymentDiscoverySource

router = APIRouter(tags=["modules"])


@router.get(
    "/projects/{project_id}/recommendations",
    response_model=list[RecommendationSchema],
)
def list_recommendations(
    project_id: UUID,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> list[RecommendationSchema]:
    project = get_project_or_404(db, project_id)
    run = latest_run(db, project.id)
    if run is None:
        return []
    recs = (
        db.query(Recommendation)
        .filter(Recommendation.analysis_run_id == run.id)
        .order_by(Recommendation.rank)
        .all()
    )
    return [
        RecommendationSchema(
            id=r.id,
            analysis_run_id=r.analysis_run_id,
            project_id=r.project_id,
            rank=r.rank,
            suggested_task=r.suggested_task,
            rationale=r.rationale,
            related_criterion_code=r.related_criterion_code,
            potential_points_delta=r.potential_points_delta,
            priority=r.priority,
            estimated_effort_hours=r.estimated_effort_hours,
            technical_risk=r.technical_risk,
            supporting_evidence_ids=r.supporting_evidence_ids,
            is_completed=r.is_completed,
        )
        for r in recs
    ]


@router.get("/projects/{project_id}/diary", response_model=DiarySnapshotSchema)
def get_diary(
    project_id: UUID,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> DiarySnapshotSchema:
    project = get_project_or_404(db, project_id)
    run = latest_run(db, project.id)
    snap: DiarySnapshot | None = None
    if run is not None:
        snap = (
            db.query(DiarySnapshot)
            .filter(DiarySnapshot.analysis_run_id == run.id)
            .order_by(DiarySnapshot.created_at.desc())
            .first()
        )
    if snap is None:
        raise HTTPException(status_code=404, detail="No diary snapshot yet")
    return DiarySnapshotSchema(
        id=snap.id,
        analysis_run_id=snap.analysis_run_id,
        project_id=snap.project_id,
        discovered_path=snap.discovered_path,
        completed_work=snap.completed_work,
        blockers=snap.blockers,
        decisions=snap.decisions,
        next_steps=snap.next_steps,
        git_alignment_summary=snap.git_alignment_summary,
        discrepancies=snap.discrepancies,
        created_at=snap.created_at,
    )


@router.get("/projects/{project_id}/security", response_model=SecurityReportSchema)
def get_security(
    project_id: UUID,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> SecurityReportSchema:
    project = get_project_or_404(db, project_id)
    report = (
        db.query(SecurityReport)
        .filter(SecurityReport.project_id == project.id)
        .order_by(SecurityReport.created_at.desc())
        .first()
    )
    if report is None:
        raise HTTPException(status_code=404, detail="No security report yet")
    return SecurityReportSchema(
        id=report.id,
        analysis_run_id=report.analysis_run_id,
        project_id=report.project_id,
        commit_sha=report.commit_sha,
        overall_status=report.overall_status,
        scanners_executed=report.scanners_executed,
        ai_executive_summary=report.ai_executive_summary,
        findings=[
            SecurityFindingSchema(
                id=f.id,
                scanner=f.scanner,
                rule_id=f.rule_id,
                severity=f.severity,
                file_path=f.file_path,
                line_number=f.line_number,
                raw_message=f.raw_message,
                ai_explanation=f.ai_explanation,
                ai_remediation=f.ai_remediation,
                priority_rank=f.priority_rank,
            )
            for f in sorted(report.findings, key=lambda x: (x.priority_rank or 999))
        ],
        created_at=report.created_at,
    )


@router.get(
    "/projects/{project_id}/deployments",
    response_model=list[DeploymentCheckSchema],
)
def list_deployments(
    project_id: UUID,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> list[DeploymentCheckSchema]:
    project = get_project_or_404(db, project_id)
    checks = (
        db.query(DeploymentCheck)
        .filter(DeploymentCheck.project_id == project.id)
        .order_by(DeploymentCheck.checked_at.desc())
        .all()
    )
    return [_check_to_schema(c) for c in checks]


def _check_to_schema(c: DeploymentCheck) -> DeploymentCheckSchema:
    return DeploymentCheckSchema(
        id=c.id,
        project_id=c.project_id,
        analysis_run_id=c.analysis_run_id,
        target_url=c.target_url,
        discovery_source=c.discovery_source,
        is_reachable=c.is_reachable,
        http_status_code=c.http_status_code,
        https_valid=c.https_valid,
        response_time_ms=c.response_time_ms,
        error_detail=c.error_detail,
        checked_at=c.checked_at,
    )


@router.post(
    "/projects/{project_id}/deployments/check",
    response_model=DeploymentCheckSchema,
    status_code=201,
)
def trigger_deployment_check(
    project_id: UUID,
    body: DeploymentCheckTriggerRequest,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> DeploymentCheckSchema:
    project = get_project_or_404(db, project_id)
    target = body.target_url or project.deployment_url
    if not target:
        raise HTTPException(
            status_code=400,
            detail="No deployment URL: set project deployment_url or pass target_url",
        )
    # SSRF note: no raw httpx here. Delegates to the monitor interface whose
    # Track 3 implementation validates resolved IPs + redirects. The stub
    # records a row without performing any network request.
    monitor = get_deployment_monitor()
    result = monitor.check(target)
    run = latest_run(db, project.id)
    check = DeploymentCheck(
        project_id=project.id,
        analysis_run_id=run.id if run else None,
        target_url=target,
        discovery_source=(
            DeploymentDiscoverySource.MANUAL
            if body.target_url
            else DeploymentDiscoverySource.CONFIG
        ),
        is_reachable=bool(result.get("is_reachable", False)),
        http_status_code=result.get("http_status_code"),
        https_valid=bool(result.get("https_valid", False)),
        response_time_ms=result.get("response_time_ms"),
        error_detail=result.get("error_detail"),
        checked_at=datetime.now(timezone.utc),
    )
    db.add(check)
    db.commit()
    db.refresh(check)
    return _check_to_schema(check)
