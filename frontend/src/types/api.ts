/**
 * Frozen TypeScript API Contract Types for DevTrack AI (/api/v1)
 * Mirrors backend/app/schemas/api_contracts.py and docs/specs/API_CONTRACT.md
 */

export type ProjectStatus = 'active' | 'paused' | 'archived' | 'completed';
export type RubricSourceType = 'builtin' | 'url' | 'pdf' | 'markdown' | 'text';
export type ScoreState = 'estimated' | 'verified' | 'needs_review';
export type DevelopmentMilestoneStatus = 'outstanding' | 'partial' | 'completed';
export type MilestoneSource = 'ai_generated' | 'user_created';
export type AnalysisTriggerType = 'initial' | 'daily' | 'manual';
export type AnalysisStatus = 'queued' | 'running' | 'completed' | 'failed';
export type EvidenceType =
  | 'commit'
  | 'source_file'
  | 'readme'
  | 'documentation'
  | 'ci_workflow'
  | 'test_result'
  | 'docker_compose'
  | 'deployment_url'
  | 'observability_config'
  | 'security_report'
  | 'agent_config'
  | 'diary_entry';
export type SecurityStatus = 'pass' | 'warning' | 'critical' | 'unknown';
export type SeverityLevel = 'info' | 'low' | 'medium' | 'high' | 'critical';
export type DeploymentDiscoverySource = 'readme' | 'config' | 'manual';
export type PriorityLevel = 'critical' | 'high' | 'medium' | 'low';
export type RiskLevel = 'low' | 'medium' | 'high';

export interface UserProfile {
  username: string;
  role: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  database: string;
  worker_status: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserProfile;
}

export interface ScoringLevelItem {
  points: number;
  description: string;
}

export interface RubricCriterion {
  id: string;
  code: string;
  name: string;
  description: string;
  display_order: number;
  max_points: number;
  scoring_levels: ScoringLevelItem[];
  required_evidence_types: string[];
}

export interface RubricSummary {
  id: string;
  slug: string;
  title: string;
  course_name: string;
  source_type: RubricSourceType;
  source_url?: string | null;
  version: string;
  retrieved_at: string;
  is_official: boolean;
  max_points: number;
  passing_threshold?: number | null;
}

export interface RubricDetail extends RubricSummary {
  raw_content?: string | null;
  criteria: RubricCriterion[];
}

export interface ExpectedScoreSummary {
  advisory_notice: string;
  estimated_points: number;
  verified_points: number;
  effective_points: number;
  potential_additional_points: number;
  max_points: number;
  passing_threshold?: number | null;
  meets_passing_threshold: boolean;
}

export interface DevelopmentProgressSummary {
  completed_tasks: number;
  partial_tasks: number;
  outstanding_tasks: number;
  total_tasks: number;
  completion_pct: number;
  milestones_approved: boolean;
}

export interface ProjectSummary {
  id: string;
  name: string;
  description?: string | null;
  github_repo_url: string;
  github_owner: string;
  github_repo: string;
  course_name: string;
  rubric_id: string;
  status: ProjectStatus;
  start_date?: string | null;
  target_date?: string | null;
  weekly_hours: number;
  diary_path?: string | null;
  deployment_url?: string | null;
  daily_schedule_cron: string;
  milestones_approved: boolean;
  last_analysis_at?: string | null;
  last_commit_sha?: string | null;
  security_status: SecurityStatus;
  deployment_reachable?: boolean | null;
  expected_score: ExpectedScoreSummary;
  development_progress: DevelopmentProgressSummary;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail extends ProjectSummary {
  latest_summary_markdown?: string | null;
  stalled_flag: boolean;
  scope_creep_flag: boolean;
}

export interface DashboardOverview {
  total_projects: number;
  active_projects: number;
  projects: ProjectSummary[];
}

export interface DevelopmentMilestone {
  id: string;
  project_id: string;
  assessment_milestone_id: string;
  title: string;
  description?: string | null;
  status: DevelopmentMilestoneStatus;
  source: MilestoneSource;
  is_approved: boolean;
  due_date?: string | null;
  estimated_effort_hours?: number | null;
  display_order: number;
  completed_at?: string | null;
}

export interface AssessmentMilestone {
  id: string;
  project_id: string;
  rubric_criterion_id: string;
  criterion_code: string;
  title: string;
  max_points: number;
  target_date?: string | null;
  is_approved: boolean;
  display_order: number;
  development_milestones: DevelopmentMilestone[];
}

export interface ProjectMilestonesResponse {
  project_id: string;
  milestones_approved: boolean;
  assessment_milestones: AssessmentMilestone[];
}

export interface AnalysisRun {
  id: string;
  project_id: string;
  trigger_type: AnalysisTriggerType;
  status: AnalysisStatus;
  commit_sha?: string | null;
  previous_commit_sha?: string | null;
  estimated_total_points: number;
  verified_total_points: number;
  max_total_points: number;
  dev_completion_pct: number;
  summary_markdown?: string | null;
  stalled_flag: boolean;
  scope_creep_flag: boolean;
  ephemeral_notification_queued: boolean;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
}

export interface EvidenceItem {
  id: string;
  analysis_run_id: string;
  project_id: string;
  evidence_type: EvidenceType;
  title: string;
  path_or_url: string;
  commit_sha?: string | null;
  snippet?: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
}

export interface CriterionAssessment {
  id: string;
  analysis_run_id: string;
  project_id: string;
  assessment_milestone_id: string;
  criterion_code: string;
  criterion_name: string;
  scoring_levels: ScoringLevelItem[];
  max_points: number;
  ai_proposed_points: number;
  ai_reasoning: string;
  ai_confidence: number;
  missing_for_next_level?: string | null;
  score_state: ScoreState;
  human_override_points?: number | null;
  human_override_reason?: string | null;
  overridden_at?: string | null;
  effective_points: number;
  evidence_items: EvidenceItem[];
}

export interface ScorecardResponse {
  project_id: string;
  analysis_run_id?: string | null;
  commit_sha?: string | null;
  rubric_title: string;
  rubric_version: string;
  rubric_source_url?: string | null;
  is_official_rubric: boolean;
  advisory_disclaimer: string;
  expected_score: ExpectedScoreSummary;
  criteria_assessments: CriterionAssessment[];
}

export interface Recommendation {
  id: string;
  analysis_run_id: string;
  project_id: string;
  rank: number;
  suggested_task: string;
  rationale: string;
  related_criterion_code: string;
  potential_points_delta: number;
  priority: PriorityLevel;
  estimated_effort_hours?: number | null;
  technical_risk: RiskLevel;
  supporting_evidence_ids: string[];
  is_completed: boolean;
}

export interface DiaryDiscrepancy {
  claim: string;
  git_reality: string;
  severity: SeverityLevel;
}

export interface DiarySnapshot {
  id: string;
  analysis_run_id: string;
  project_id: string;
  discovered_path: string;
  completed_work: string[];
  blockers: string[];
  decisions: string[];
  next_steps: string[];
  git_alignment_summary: string;
  discrepancies: DiaryDiscrepancy[];
  created_at: string;
}

export interface SecurityFinding {
  id: string;
  scanner: string;
  rule_id: string;
  severity: SeverityLevel;
  file_path?: string | null;
  line_number?: number | null;
  raw_message: string;
  ai_explanation?: string | null;
  ai_remediation?: string | null;
  priority_rank?: number | null;
}

export interface SecurityReport {
  id: string;
  analysis_run_id: string;
  project_id: string;
  commit_sha: string;
  overall_status: SecurityStatus;
  scanners_executed: string[];
  ai_executive_summary: string;
  findings: SecurityFinding[];
  created_at: string;
}

export interface DeploymentCheck {
  id: string;
  project_id: string;
  analysis_run_id?: string | null;
  target_url: string;
  discovery_source: DeploymentDiscoverySource;
  is_reachable: boolean;
  http_status_code?: number | null;
  https_valid: boolean;
  response_time_ms?: number | null;
  error_detail?: string | null;
  checked_at: string;
}

export interface TelemetryCitation {
  source: string;
  query: string;
  excerpt: string;
}

export interface OnCallDiagnosisResponse {
  incident_summary: string;
  root_cause_hypothesis: string;
  confidence: number;
  evidence_citations: TelemetryCitation[];
  recommended_actions: string[];
  read_only_verified: boolean;
}

// ---------------------------------------------------------------------------
// Request payloads (mirror backend/app/schemas/api_contracts.py request models)
// ---------------------------------------------------------------------------

export interface ProjectCreateRequest {
  name: string;
  description?: string | null;
  github_repo_url: string;
  course_name?: string;
  rubric_id?: string | null;
  start_date?: string | null;
  target_date?: string | null;
  weekly_hours?: number;
  diary_path?: string | null;
  deployment_url?: string | null;
  daily_schedule_cron?: string;
}

export interface ProjectUpdateRequest {
  name?: string | null;
  description?: string | null;
  status?: ProjectStatus | null;
  start_date?: string | null;
  target_date?: string | null;
  weekly_hours?: number | null;
  diary_path?: string | null;
  deployment_url?: string | null;
  daily_schedule_cron?: string | null;
}

export interface MilestoneApprovalRequest {
  approve_all: boolean;
  assessment_milestone_ids?: string[];
  development_milestone_ids?: string[];
}

export interface DevelopmentMilestoneCreateRequest {
  assessment_milestone_id: string;
  title: string;
  description?: string | null;
  due_date?: string | null;
  estimated_effort_hours?: number | null;
}

export interface DevelopmentMilestoneUpdateRequest {
  title?: string | null;
  description?: string | null;
  status?: DevelopmentMilestoneStatus | null;
  due_date?: string | null;
  estimated_effort_hours?: number | null;
}

export interface TriggerAnalysisRequest {
  notify_email_once?: string | null;
  acknowledge_ephemeral_email: boolean;
}

export interface ScoreOverrideRequest {
  score_state: ScoreState;
  human_override_points?: number | null;
  human_override_reason?: string | null;
}

export interface RubricIngestRequest {
  title: string;
  course_name: string;
  source_type: RubricSourceType;
  source_url?: string | null;
  raw_content?: string | null;
  version?: string;
}

export interface OnCallDiagnoseRequest {
  alert_name: string;
  time_window_minutes?: number;
  context_notes?: string | null;
}

export interface DeploymentCheckTriggerRequest {
  target_url?: string | null;
}

