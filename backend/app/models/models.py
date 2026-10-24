"""SQLAlchemy 2.0 ORM models for all tables in docs/specs/DATABASE_SCHEMA.md.

Covers §3.1–3.12: rubrics, rubric_criteria, projects, assessment_milestones,
development_milestones, analysis_runs, evidence_items, criterion_assessments,
diary_snapshots, security_reports, security_findings, deployment_checks,
recommendations (13 tables).

Portability: UUID PKs via sqlalchemy.Uuid, enums with native_enum=False,
JSON columns via sqlalchemy.JSON (JSONB on PostgreSQL, TEXT on SQLite).

INVARIANTS (backend/AGENTS.md §2):
- Zero persistent email storage: NO email column exists on any model.
- Assessment vs Development separation: completing development_milestones
  must NEVER auto-award criterion_assessments points (enforced in endpoints).
- Score override preservation: ai_proposed_points/ai_reasoning are immutable;
  only human_override_* + score_state + overridden_at change on override.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.schemas.enums import (
    AnalysisStatus,
    AnalysisTriggerType,
    DeploymentDiscoverySource,
    DevelopmentMilestoneStatus,
    EvidenceType,
    MilestoneSource,
    PriorityLevel,
    ProjectStatus,
    RiskLevel,
    RubricSourceType,
    ScoreState,
    SecurityStatus,
    SeverityLevel,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 3.1 rubrics (immutable once versioned: updates create a NEW row/version)
# ---------------------------------------------------------------------------
class Rubric(Base):
    __tablename__ = "rubrics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(255))
    course_name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[RubricSourceType] = mapped_column(
        SqlEnum(RubricSourceType, native_enum=False, length=32)
    )
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(50))
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    max_points: Mapped[int] = mapped_column(Integer, default=24)
    passing_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    criteria: Mapped[list[RubricCriterion]] = relationship(
        back_populates="rubric", cascade="all, delete-orphan", passive_deletes=True
    )
    projects: Mapped[list[Project]] = relationship(back_populates="rubric")


# ---------------------------------------------------------------------------
# 3.2 rubric_criteria
# ---------------------------------------------------------------------------
class RubricCriterion(Base):
    __tablename__ = "rubric_criteria"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rubric_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rubrics.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer)
    max_points: Mapped[int] = mapped_column(Integer)
    # List of {points: int, description: str} (JSONB on PostgreSQL).
    scoring_levels: Mapped[list] = mapped_column(JSON, default=list)
    required_evidence_types: Mapped[list] = mapped_column(JSON, default=list)

    rubric: Mapped[Rubric] = relationship(back_populates="criteria")


# ---------------------------------------------------------------------------
# 3.3 projects (single predefined account owns all projects; NO email column)
# ---------------------------------------------------------------------------
class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_repo_url: Mapped[str] = mapped_column(String(512))
    github_owner: Mapped[str] = mapped_column(String(128))
    github_repo: Mapped[str] = mapped_column(String(128))
    default_branch: Mapped[str] = mapped_column(String(128), default="main")
    course_name: Mapped[str] = mapped_column(String(255))
    rubric_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("rubrics.id"))
    status: Mapped[ProjectStatus] = mapped_column(
        SqlEnum(ProjectStatus, native_enum=False, length=32),
        default=ProjectStatus.ACTIVE,
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    weekly_hours: Mapped[int] = mapped_column(Integer, default=10)
    diary_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    deployment_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    daily_schedule_cron: Mapped[str] = mapped_column(String(64), default="0 6 * * *")
    milestones_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    last_analysis_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    rubric: Mapped[Rubric] = relationship(back_populates="projects")
    assessment_milestones: Mapped[list[AssessmentMilestone]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    development_milestones: Mapped[list[DevelopmentMilestone]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    analysis_runs: Mapped[list[AnalysisRun]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    deployment_checks: Mapped[list[DeploymentCheck]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


# ---------------------------------------------------------------------------
# 3.4 assessment_milestones (official rubric criteria, approval-gated)
# ---------------------------------------------------------------------------
class AssessmentMilestone(Base):
    __tablename__ = "assessment_milestones"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    rubric_criterion_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rubric_criteria.id")
    )
    title: Mapped[str] = mapped_column(String(255))
    max_points: Mapped[int] = mapped_column(Integer)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[Project] = relationship(back_populates="assessment_milestones")
    rubric_criterion: Mapped[RubricCriterion] = relationship()
    development_milestones: Mapped[list[DevelopmentMilestone]] = relationship(
        back_populates="assessment_milestone",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    criterion_assessments: Mapped[list[CriterionAssessment]] = relationship(
        back_populates="assessment_milestone",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


# ---------------------------------------------------------------------------
# 3.5 development_milestones (actionable tasks; completing them NEVER
# awards assessment points — enforced in the PATCH endpoint).
# ---------------------------------------------------------------------------
class DevelopmentMilestone(Base):
    __tablename__ = "development_milestones"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    assessment_milestone_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("assessment_milestones.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[DevelopmentMilestoneStatus] = mapped_column(
        SqlEnum(DevelopmentMilestoneStatus, native_enum=False, length=32),
        default=DevelopmentMilestoneStatus.OUTSTANDING,
    )
    source: Mapped[MilestoneSource] = mapped_column(
        SqlEnum(MilestoneSource, native_enum=False, length=32),
        default=MilestoneSource.AI_GENERATED,
    )
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_effort_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    project: Mapped[Project] = relationship(back_populates="development_milestones")
    assessment_milestone: Mapped[AssessmentMilestone] = relationship(
        back_populates="development_milestones"
    )


# ---------------------------------------------------------------------------
# 3.6 analysis_runs (PostgreSQL-backed job queue record; NO email column —
# one-time notify emails live only in the EPHEMERAL_NOTIFICATIONS RAM map).
# ---------------------------------------------------------------------------
class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    trigger_type: Mapped[AnalysisTriggerType] = mapped_column(
        SqlEnum(AnalysisTriggerType, native_enum=False, length=32),
        default=AnalysisTriggerType.MANUAL,
    )
    status: Mapped[AnalysisStatus] = mapped_column(
        SqlEnum(AnalysisStatus, native_enum=False, length=32),
        default=AnalysisStatus.QUEUED,
    )
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    estimated_total_points: Mapped[int] = mapped_column(Integer, default=0)
    verified_total_points: Mapped[int] = mapped_column(Integer, default=0)
    max_total_points: Mapped[int] = mapped_column(Integer, default=24)
    dev_completion_pct: Mapped[float] = mapped_column(Float, default=0.0)
    summary_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    stalled_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    scope_creep_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    project: Mapped[Project] = relationship(back_populates="analysis_runs")
    evidence_items: Mapped[list[EvidenceItem]] = relationship(
        back_populates="analysis_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    criterion_assessments: Mapped[list[CriterionAssessment]] = relationship(
        back_populates="analysis_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    diary_snapshots: Mapped[list[DiarySnapshot]] = relationship(
        back_populates="analysis_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    security_reports: Mapped[list[SecurityReport]] = relationship(
        back_populates="analysis_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    recommendations: Mapped[list[Recommendation]] = relationship(
        back_populates="analysis_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


# ---------------------------------------------------------------------------
# 3.7 evidence_items
# ---------------------------------------------------------------------------
class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    evidence_type: Mapped[EvidenceType] = mapped_column(
        SqlEnum(EvidenceType, native_enum=False, length=32)
    )
    title: Mapped[str] = mapped_column(String(255))
    path_or_url: Mapped[str] = mapped_column(String(1024))
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="evidence_items")


# ---------------------------------------------------------------------------
# 3.8 criterion_assessments — effective_points is DERIVED, never stored:
# human_override_points if not None else ai_proposed_points.
# ---------------------------------------------------------------------------
class CriterionAssessment(Base):
    __tablename__ = "criterion_assessments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    assessment_milestone_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("assessment_milestones.id", ondelete="CASCADE"), index=True
    )
    criterion_code: Mapped[str] = mapped_column(String(100))
    max_points: Mapped[int] = mapped_column(Integer)
    ai_proposed_points: Mapped[int] = mapped_column(Integer)
    ai_reasoning: Mapped[str] = mapped_column(Text)
    ai_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    missing_for_next_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_state: Mapped[ScoreState] = mapped_column(
        SqlEnum(ScoreState, native_enum=False, length=32),
        default=ScoreState.ESTIMATED,
    )
    human_override_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    human_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)

    analysis_run: Mapped[AnalysisRun] = relationship(
        back_populates="criterion_assessments"
    )
    assessment_milestone: Mapped[AssessmentMilestone] = relationship(
        back_populates="criterion_assessments"
    )

    @property
    def effective_points(self) -> int:
        return (
            self.human_override_points
            if self.human_override_points is not None
            else self.ai_proposed_points
        )


# ---------------------------------------------------------------------------
# 3.9 diary_snapshots
# ---------------------------------------------------------------------------
class DiarySnapshot(Base):
    __tablename__ = "diary_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    discovered_path: Mapped[str] = mapped_column(String(512))
    completed_work: Mapped[list] = mapped_column(JSON, default=list)
    blockers: Mapped[list] = mapped_column(JSON, default=list)
    decisions: Mapped[list] = mapped_column(JSON, default=list)
    next_steps: Mapped[list] = mapped_column(JSON, default=list)
    git_alignment_summary: Mapped[str] = mapped_column(Text, default="")
    discrepancies: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="diary_snapshots")


# ---------------------------------------------------------------------------
# 3.10 security_reports & security_findings (raw_message pre-redacted of
# secret values by Track 3 before persistence).
# ---------------------------------------------------------------------------
class SecurityReport(Base):
    __tablename__ = "security_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    commit_sha: Mapped[str] = mapped_column(String(64))
    overall_status: Mapped[SecurityStatus] = mapped_column(
        SqlEnum(SecurityStatus, native_enum=False, length=32),
        default=SecurityStatus.UNKNOWN,
    )
    scanners_executed: Mapped[list] = mapped_column(JSON, default=list)
    ai_executive_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    analysis_run: Mapped[AnalysisRun] = relationship(
        back_populates="security_reports"
    )
    findings: Mapped[list[SecurityFinding]] = relationship(
        back_populates="security_report",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SecurityFinding(Base):
    __tablename__ = "security_findings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    security_report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("security_reports.id", ondelete="CASCADE"), index=True
    )
    scanner: Mapped[str] = mapped_column(String(64))
    rule_id: Mapped[str] = mapped_column(String(255))
    severity: Mapped[SeverityLevel] = mapped_column(
        SqlEnum(SeverityLevel, native_enum=False, length=32),
        default=SeverityLevel.INFO,
    )
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_message: Mapped[str] = mapped_column(Text)
    ai_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    security_report: Mapped[SecurityReport] = relationship(back_populates="findings")


# ---------------------------------------------------------------------------
# 3.11 deployment_checks (SSRF-safe checks performed by Track 3's monitor;
# Track 1 only records rows via the Protocol stub).
# ---------------------------------------------------------------------------
class DeploymentCheck(Base):
    __tablename__ = "deployment_checks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=True
    )
    target_url: Mapped[str] = mapped_column(String(512))
    discovery_source: Mapped[DeploymentDiscoverySource] = mapped_column(
        SqlEnum(DeploymentDiscoverySource, native_enum=False, length=32),
        default=DeploymentDiscoverySource.MANUAL,
    )
    is_reachable: Mapped[bool] = mapped_column(Boolean, default=False)
    http_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    https_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    project: Mapped[Project] = relationship(back_populates="deployment_checks")


# ---------------------------------------------------------------------------
# 3.12 recommendations (AI Project Mentor output; official criteria stay
# separate — recommendations never carry official grades).
# ---------------------------------------------------------------------------
class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    rank: Mapped[int] = mapped_column(Integer)
    suggested_task: Mapped[str] = mapped_column(String(255))
    rationale: Mapped[str] = mapped_column(Text)
    related_criterion_code: Mapped[str] = mapped_column(String(100))
    potential_points_delta: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[PriorityLevel] = mapped_column(
        SqlEnum(PriorityLevel, native_enum=False, length=32),
        default=PriorityLevel.MEDIUM,
    )
    estimated_effort_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    technical_risk: Mapped[RiskLevel] = mapped_column(
        SqlEnum(RiskLevel, native_enum=False, length=32),
        default=RiskLevel.LOW,
    )
    supporting_evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="recommendations")
