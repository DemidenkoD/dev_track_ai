"""Structured Pydantic output schemas for DevTrack AI's specialized Gemini agents."""

from pydantic import BaseModel, Field, model_validator

from app.schemas.enums import (
    EvidenceType,
    PriorityLevel,
    RiskLevel,
    ScoreState,
    SecurityStatus,
    SeverityLevel,
)


# ------------------------------------------------------------------------------
# 1. Rubric Analyst Output Schemas
# ------------------------------------------------------------------------------
class ScoringLevelItem(BaseModel):
    points: int = Field(..., ge=0, description="Point value for this scoring level")
    description: str = Field(..., description="Official description for earning these points")


class ExtractedCriterionItem(BaseModel):
    code: str = Field(..., description="Snake_case identifier for the criterion")
    name: str = Field(..., description="Official display name of the criterion")
    description: str = Field(..., description="Summary of what the criterion evaluates")
    display_order: int = Field(..., ge=1)
    max_points: int = Field(..., ge=1)
    scoring_levels: list[ScoringLevelItem]
    required_evidence_types: list[EvidenceType] = Field(default_factory=list)


class ExtractedRubricOutput(BaseModel):
    title: str
    course_name: str
    max_points: int
    passing_threshold: int | None = None
    criteria: list[ExtractedCriterionItem]


class CriterionScoreProposal(BaseModel):
    criterion_code: str
    ai_proposed_points: int = Field(..., ge=0)
    max_points: int = Field(..., ge=1)
    score_state: ScoreState = Field(
        default=ScoreState.ESTIMATED,
        description="estimated, verified, or needs_review when evidence is incomplete/ambiguous",
    )
    ai_confidence: float = Field(..., ge=0.0, le=1.0)
    ai_reasoning: str = Field(
        ..., description="Evidence-backed justification citing concrete files/commits"
    )
    missing_for_next_level: str | None = Field(
        default=None, description="Specific gap preventing the next scoring level"
    )
    cited_evidence_paths: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _enforce_score_state_guards(self) -> "CriterionScoreProposal":
        """Score-state grounding guards (Track 2 rubric-evaluation skill).

        - ``verified`` requires non-empty evidence (no guessing).
        - ``needs_review`` requires low confidence (< 0.70); high confidence
          with missing/ambiguous evidence must be ``estimated`` or lower it.
        """
        if self.score_state == ScoreState.VERIFIED and not self.cited_evidence_paths:
            raise ValueError(
                f"score_state='verified' forbidden with empty cited_evidence_paths "
                f"for criterion `{self.criterion_code}`; use 'estimated' or "
                f"'needs_review' with concrete evidence paths."
            )
        if self.score_state == ScoreState.NEEDS_REVIEW and self.ai_confidence >= 0.70:
            raise ValueError(
                f"score_state='needs_review' forbidden with ai_confidence>=0.70 "
                f"({self.ai_confidence}) for criterion `{self.criterion_code}`; "
                f"cap confidence below 0.70 when evidence is missing/ambiguous."
            )
        return self


class ScorecardEvaluationOutput(BaseModel):
    criteria_evaluations: list[CriterionScoreProposal]
    overall_assessment_summary: str


# ------------------------------------------------------------------------------
# 2. Progress Analyst Output Schemas
# ------------------------------------------------------------------------------
class GeneratedDevTaskItem(BaseModel):
    criterion_code: str
    title: str
    description: str
    estimated_effort_hours: float = Field(default=2.0, ge=0.5)


class MilestonePlanGenerationOutput(BaseModel):
    development_tasks: list[GeneratedDevTaskItem]


class ProgressEvaluationOutput(BaseModel):
    completed_task_titles: list[str] = Field(default_factory=list)
    partial_task_titles: list[str] = Field(default_factory=list)
    outstanding_task_titles: list[str] = Field(default_factory=list)
    dev_completion_pct: float = Field(..., ge=0.0, le=100.0)
    deadline_adherence_summary: str
    stalled_development_detected: bool = False
    scope_creep_detected: bool = False


# ------------------------------------------------------------------------------
# 3. Diary Analyst Output Schemas
# ------------------------------------------------------------------------------
class DiaryDiscrepancyItem(BaseModel):
    claim: str = Field(..., description="What the development diary claims")
    git_reality: str = Field(..., description="What the Git commit history / codebase shows")
    severity: SeverityLevel = Field(default=SeverityLevel.LOW)


class DiaryAnalysisOutput(BaseModel):
    completed_work: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    git_alignment_summary: str
    discrepancies: list[DiaryDiscrepancyItem] = Field(default_factory=list)


# ------------------------------------------------------------------------------
# 4. Security Reviewer Output Schemas
# ------------------------------------------------------------------------------
class ExplainedSecurityFinding(BaseModel):
    scanner: str
    rule_id: str
    severity: SeverityLevel
    file_path: str | None = None
    line_number: int | None = None
    ai_explanation: str
    ai_remediation: str
    priority_rank: int = Field(..., ge=1)


class SecurityReviewOutput(BaseModel):
    overall_status: SecurityStatus
    ai_executive_summary: str
    prioritized_findings: list[ExplainedSecurityFinding] = Field(default_factory=list)


# ------------------------------------------------------------------------------
# 5. Project Mentor / Orchestrator Output Schemas
# ------------------------------------------------------------------------------
class RecommendationItem(BaseModel):
    rank: int = Field(..., ge=1)
    suggested_task: str
    rationale: str
    related_criterion_code: str
    potential_points_delta: int = Field(..., ge=0)
    priority: PriorityLevel
    estimated_effort_hours: float = Field(default=2.0, ge=0.25)
    technical_risk: RiskLevel = Field(default=RiskLevel.LOW)
    supporting_evidence_paths: list[str] = Field(default_factory=list)


class MentorEvaluationOutput(BaseModel):
    executive_summary_markdown: str
    stalled_flag: bool = False
    scope_creep_flag: bool = False
    recommendations: list[RecommendationItem] = Field(default_factory=list)


# ------------------------------------------------------------------------------
# 6. Bounded Read-Only On-Call Agent Output Schema (Phase 4)
# ------------------------------------------------------------------------------
class TelemetryCitation(BaseModel):
    source: str = Field(..., description="prometheus, loki, tempo, or postgres_jobs")
    query: str
    excerpt: str


class OnCallDiagnosisOutput(BaseModel):
    incident_summary: str
    root_cause_hypothesis: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_citations: list[TelemetryCitation] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    read_only_verified: bool = True

