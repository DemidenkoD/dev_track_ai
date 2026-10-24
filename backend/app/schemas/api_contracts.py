"""Frozen OpenAPI 3.1 REST request/response contract schemas for DevTrack AI."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.agent_outputs import (
    DiaryDiscrepancyItem,
    ScoringLevelItem,
    TelemetryCitation,
)
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


# ------------------------------------------------------------------------------
# Health & Authentication
# ------------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.3.0"
    database: str = "connected"
    worker_status: str = "active"


class LoginRequest(BaseModel):
    username: str
    password: str


class UserProfileSchema(BaseModel):
    username: str
    role: str = "reviewer"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400
    user: UserProfileSchema


# ------------------------------------------------------------------------------
# Rubrics
# ------------------------------------------------------------------------------
class RubricCriterionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str
    display_order: int
    max_points: int
    scoring_levels: list[ScoringLevelItem]
    required_evidence_types: list[str] = Field(default_factory=list)


class RubricSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    title: str
    course_name: str
    source_type: RubricSourceType
    source_url: str | None = None
    version: str
    retrieved_at: datetime
    is_official: bool
    max_points: int
    passing_threshold: int | None = None


class RubricDetailSchema(RubricSummarySchema):
    raw_content: str | None = None
    criteria: list[RubricCriterionSchema] = Field(default_factory=list)


class RubricIngestRequest(BaseModel):
    title: str
    course_name: str
    source_type: RubricSourceType = RubricSourceType.MARKDOWN
    source_url: str | None = None
    raw_content: str | None = None
    version: str = "1.0.0"


# ------------------------------------------------------------------------------
# Projects & Dashboard
# ------------------------------------------------------------------------------
class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = None
    github_repo_url: str = Field(
        ..., description="Public GitHub URL: https://github.com/<owner>/<repo>"
    )
    course_name: str = "AI Dev Tools Zoomcamp 2026"
    rubric_id: UUID | None = None
    start_date: date | None = None
    target_date: date | None = None
    weekly_hours: int = Field(default=10, ge=1, le=100)
    diary_path: str | None = None
    deployment_url: str | None = None
    daily_schedule_cron: str = "0 6 * * *"


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None
    start_date: date | None = None
    target_date: date | None = None
    weekly_hours: int | None = Field(default=None, ge=1, le=100)
    diary_path: str | None = None
    deployment_url: str | None = None
    daily_schedule_cron: str | None = None


class ExpectedScoreSummarySchema(BaseModel):
    """Explicit separation of estimated vs verified points; never presented as an official grade."""

    advisory_notice: str = (
        "AI estimates are advisory and never constitute an official course grade."
    )
    estimated_points: int = 0
    verified_points: int = 0
    effective_points: int = 0
    potential_additional_points: int = 24
    max_points: int = 24
    passing_threshold: int | None = 10
    meets_passing_threshold: bool = False


class DevelopmentProgressSummarySchema(BaseModel):
    """Separate development task completion dimension."""

    completed_tasks: int = 0
    partial_tasks: int = 0
    outstanding_tasks: int = 0
    total_tasks: int = 0
    completion_pct: float = 0.0
    milestones_approved: bool = False


class ProjectSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    github_repo_url: str
    github_owner: str
    github_repo: str
    course_name: str
    rubric_id: UUID
    status: ProjectStatus
    start_date: date | None = None
    target_date: date | None = None
    weekly_hours: int
    diary_path: str | None = None
    deployment_url: str | None = None
    daily_schedule_cron: str
    milestones_approved: bool
    last_analysis_at: datetime | None = None
    last_commit_sha: str | None = None
    # No report yet → degraded-safe WARNING (DATABASE_SCHEMA §3.10 has no "unknown").
    security_status: SecurityStatus = SecurityStatus.WARNING
    deployment_reachable: bool | None = None
    expected_score: ExpectedScoreSummarySchema = Field(
        default_factory=ExpectedScoreSummarySchema
    )
    development_progress: DevelopmentProgressSummarySchema = Field(
        default_factory=DevelopmentProgressSummarySchema
    )
    created_at: datetime
    updated_at: datetime


class ProjectDetailSchema(ProjectSummarySchema):
    latest_summary_markdown: str | None = None
    stalled_flag: bool = False
    scope_creep_flag: bool = False


class DashboardOverviewSchema(BaseModel):
    total_projects: int
    active_projects: int
    projects: list[ProjectSummarySchema]


# ------------------------------------------------------------------------------
# Milestones (Assessment vs Development)
# ------------------------------------------------------------------------------
class DevelopmentMilestoneSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    assessment_milestone_id: UUID
    title: str
    description: str | None = None
    status: DevelopmentMilestoneStatus
    source: MilestoneSource
    is_approved: bool
    due_date: date | None = None
    estimated_effort_hours: float | None = None
    display_order: int
    completed_at: datetime | None = None


class AssessmentMilestoneSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    rubric_criterion_id: UUID
    criterion_code: str = ""
    title: str
    max_points: int
    target_date: date | None = None
    is_approved: bool
    display_order: int
    development_milestones: list[DevelopmentMilestoneSchema] = Field(
        default_factory=list
    )


class ProjectMilestonesResponse(BaseModel):
    project_id: UUID
    milestones_approved: bool
    assessment_milestones: list[AssessmentMilestoneSchema]


class MilestoneApprovalRequest(BaseModel):
    approve_all: bool = True
    assessment_milestone_ids: list[UUID] = Field(default_factory=list)
    development_milestone_ids: list[UUID] = Field(default_factory=list)


class DevelopmentMilestoneCreateRequest(BaseModel):
    assessment_milestone_id: UUID
    title: str
    description: str | None = None
    due_date: date | None = None
    estimated_effort_hours: float | None = 2.0


class DevelopmentMilestoneUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: DevelopmentMilestoneStatus | None = None
    due_date: date | None = None
    estimated_effort_hours: float | None = None


# ------------------------------------------------------------------------------
# Analysis Runs & Ephemeral One-Time Notification
# ------------------------------------------------------------------------------
class TriggerAnalysisRequest(BaseModel):
    """Note: notify_email_once is held in volatile RAM only and never persisted."""

    notify_email_once: EmailStr | None = Field(
        default=None,
        description="Optional one-time email held strictly in memory while job is pending.",
    )
    acknowledge_ephemeral_email: bool = Field(
        default=False,
        description="User acknowledges email is used once and never persisted.",
    )


class AnalysisRunSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    trigger_type: AnalysisTriggerType
    status: AnalysisStatus
    commit_sha: str | None = None
    previous_commit_sha: str | None = None
    estimated_total_points: int
    verified_total_points: int
    max_total_points: int
    dev_completion_pct: float
    summary_markdown: str | None = None
    stalled_flag: bool = False
    scope_creep_flag: bool = False
    ephemeral_notification_queued: bool = False
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


# ------------------------------------------------------------------------------
# Evidence & Rubric Scorecard
# ------------------------------------------------------------------------------
class EvidenceItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_run_id: UUID
    project_id: UUID
    evidence_type: EvidenceType
    title: str
    path_or_url: str
    commit_sha: str | None = None
    snippet: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class CriterionAssessmentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_run_id: UUID
    project_id: UUID
    assessment_milestone_id: UUID
    criterion_code: str
    criterion_name: str = ""
    scoring_levels: list[ScoringLevelItem] = Field(default_factory=list)
    max_points: int
    ai_proposed_points: int
    ai_reasoning: str
    ai_confidence: float
    missing_for_next_level: str | None = None
    score_state: ScoreState
    human_override_points: int | None = None
    human_override_reason: str | None = None
    overridden_at: datetime | None = None
    effective_points: int = 0
    evidence_items: list[EvidenceItemSchema] = Field(default_factory=list)


class ScorecardResponse(BaseModel):
    project_id: UUID
    analysis_run_id: UUID | None = None
    commit_sha: str | None = None
    rubric_title: str
    rubric_version: str
    rubric_source_url: str | None = None
    is_official_rubric: bool = True
    advisory_disclaimer: str = (
        "Expected course scores are advisory AI estimates and never official course grades."
    )
    expected_score: ExpectedScoreSummarySchema
    criteria_assessments: list[CriterionAssessmentSchema]


class ScoreOverrideRequest(BaseModel):
    score_state: ScoreState = ScoreState.VERIFIED
    human_override_points: int | None = Field(default=None, ge=0)
    human_override_reason: str | None = None


# ------------------------------------------------------------------------------
# Recommendations, Diary, Security & Deployment
# ------------------------------------------------------------------------------
class RecommendationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_run_id: UUID
    project_id: UUID
    rank: int
    suggested_task: str
    rationale: str
    related_criterion_code: str
    potential_points_delta: int
    priority: PriorityLevel
    estimated_effort_hours: float | None = None
    technical_risk: RiskLevel
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    is_completed: bool = False


class DiarySnapshotSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_run_id: UUID
    project_id: UUID
    discovered_path: str
    completed_work: list[str]
    blockers: list[str]
    decisions: list[str]
    next_steps: list[str]
    git_alignment_summary: str
    discrepancies: list[DiaryDiscrepancyItem]
    created_at: datetime


class SecurityFindingSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scanner: str
    rule_id: str
    severity: SeverityLevel
    file_path: str | None = None
    line_number: int | None = None
    raw_message: str
    ai_explanation: str | None = None
    ai_remediation: str | None = None
    priority_rank: int | None = None


class SecurityReportSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_run_id: UUID
    project_id: UUID
    commit_sha: str
    overall_status: SecurityStatus
    scanners_executed: list[str]
    ai_executive_summary: str
    findings: list[SecurityFindingSchema] = Field(default_factory=list)
    created_at: datetime


class DeploymentCheckSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    analysis_run_id: UUID | None = None
    target_url: str
    discovery_source: DeploymentDiscoverySource
    is_reachable: bool
    http_status_code: int | None = None
    https_valid: bool
    response_time_ms: float | None = None
    error_detail: str | None = None
    checked_at: datetime


class DeploymentCheckTriggerRequest(BaseModel):
    target_url: str | None = None


# ------------------------------------------------------------------------------
# Phase 4: Bounded Read-Only On-Call Agent
# ------------------------------------------------------------------------------
class OnCallDiagnoseRequest(BaseModel):
    alert_name: str
    time_window_minutes: int = Field(default=30, ge=5, le=1440)
    context_notes: str | None = None


class OnCallDiagnosisResponse(BaseModel):
    incident_summary: str
    root_cause_hypothesis: str
    confidence: float
    evidence_citations: list[TelemetryCitation]
    recommended_actions: list[str]
    read_only_verified: bool = True

