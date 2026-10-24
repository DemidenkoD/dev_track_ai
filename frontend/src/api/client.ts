/**
 * DevTrack AI — centralised HTTP client for `/api/v1`.
 *
 * CONTRACT RULE: this module is the SOLE place in the frontend that performs
 * `fetch()` calls against `/api/v1`. All pages/components/hooks MUST import
 * from this module and MUST NOT call fetch() directly.
 *
 * Types mirror `docs/specs/API_CONTRACT.md` and
 * `backend/app/schemas/api_contracts.py` (see `src/types/api.ts`).
 */
import type {
  AnalysisRun,
  AssessmentMilestone,
  CriterionAssessment,
  DashboardOverview,
  DeploymentCheck,
  DeploymentCheckTriggerRequest,
  DevelopmentMilestone,
  DevelopmentMilestoneCreateRequest,
  DevelopmentMilestoneUpdateRequest,
  DiarySnapshot,
  EvidenceItem,
  HealthResponse,
  LoginRequest,
  MilestoneApprovalRequest,
  OnCallDiagnoseRequest,
  OnCallDiagnosisResponse,
  ProjectCreateRequest,
  ProjectDetail,
  ProjectMilestonesResponse,
  ProjectSummary,
  ProjectUpdateRequest,
  Recommendation,
  RubricDetail,
  RubricIngestRequest,
  RubricSummary,
  ScoreOverrideRequest,
  ScorecardResponse,
  SecurityReport,
  TokenResponse,
  TriggerAnalysisRequest,
  UserProfile,
} from '../types/api';

const TOKEN_STORAGE_KEY = 'devtrack.auth.token';

export function getStoredToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
    else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // Storage unavailable (private mode) — token stays in memory only.
  }
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  auth?: boolean;
  query?: Record<string, string | number | boolean | undefined | null>;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const search =
    query == null
      ? ''
      : Object.entries(query)
          .filter(([, v]) => v !== undefined && v !== null && v !== '')
          .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
          .join('&');
  return search ? `${path}?${search}` : path;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, auth = true, query } = opts;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (auth) {
    const token = getStoredToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }
  const res = await fetch(buildUrl(path, query), {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const contentType = res.headers.get('content-type') ?? '';
  const payload: unknown = contentType.includes('application/json')
    ? await res.json().catch(() => null)
    : await res.text().catch(() => null);
  if (!res.ok) {
    const message =
      payload != null && typeof payload === 'object' && 'detail' in payload
        ? String((payload as { detail: unknown }).detail)
        : `Request failed with status ${res.status}`;
    throw new ApiError(res.status, message, payload);
  }
  return payload as T;
}

// ---------------------------------------------------------------------------
// Auth & health
// ---------------------------------------------------------------------------

export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/api/v1/health', { auth: false });
}

export async function login(credentials: LoginRequest): Promise<TokenResponse> {
  const token = await request<TokenResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: credentials,
    auth: false,
  });
  setStoredToken(token.access_token);
  return token;
}

export function logout(): void {
  setStoredToken(null);
}

export async function fetchCurrentUser(): Promise<UserProfile> {
  return request<UserProfile>('/api/v1/auth/me');
}

// ---------------------------------------------------------------------------
// Rubrics
// ---------------------------------------------------------------------------

export async function listRubrics(): Promise<RubricSummary[]> {
  return request<RubricSummary[]>('/api/v1/rubrics');
}

export async function getRubric(rubricId: string): Promise<RubricDetail> {
  return request<RubricDetail>(`/api/v1/rubrics/${encodeURIComponent(rubricId)}`);
}

export async function ingestRubric(payload: RubricIngestRequest): Promise<RubricDetail> {
  return request<RubricDetail>('/api/v1/rubrics/ingest', { method: 'POST', body: payload });
}

// ---------------------------------------------------------------------------
// Projects & dashboard
// ---------------------------------------------------------------------------

export async function fetchDashboard(): Promise<DashboardOverview> {
  return request<DashboardOverview>('/api/v1/dashboard');
}

export async function listProjects(status?: string): Promise<ProjectSummary[]> {
  return request<ProjectSummary[]>('/api/v1/projects', {
    query: status ? { status } : undefined,
  });
}

/**
 * SSRF guard (client-side hint only — backend re-validates): only allow
 * public `https://github.com/<owner>/<repo>` URLs in project forms.
 */
export function isAllowedGitHubRepoUrl(url: string): boolean {
  const trimmed = url.trim();
  const match = /^https:\/\/github\.com\/([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+?)(?:\.git)?\/?$/.exec(trimmed);
  return match != null;
}

export async function createProject(payload: ProjectCreateRequest): Promise<ProjectDetail> {
  if (!isAllowedGitHubRepoUrl(payload.github_repo_url)) {
    throw new ApiError(
      400,
      'Only public GitHub repository URLs (https://github.com/<owner>/<repo>) are permitted.',
    );
  }
  return request<ProjectDetail>('/api/v1/projects', { method: 'POST', body: payload });
}

export async function getProject(projectId: string): Promise<ProjectDetail> {
  return request<ProjectDetail>(`/api/v1/projects/${encodeURIComponent(projectId)}`);
}

export async function updateProject(
  projectId: string,
  payload: ProjectUpdateRequest,
): Promise<ProjectDetail> {
  return request<ProjectDetail>(`/api/v1/projects/${encodeURIComponent(projectId)}`, {
    method: 'PATCH',
    body: payload,
  });
}

export async function deleteProject(projectId: string): Promise<void> {
  await request<unknown>(`/api/v1/projects/${encodeURIComponent(projectId)}`, {
    method: 'DELETE',
  });
}

// ---------------------------------------------------------------------------
// Milestones (two-level: assessment vs development)
// ---------------------------------------------------------------------------

export async function fetchMilestones(projectId: string): Promise<ProjectMilestonesResponse> {
  return request<ProjectMilestonesResponse>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/milestones`,
  );
}

export async function approveMilestones(
  projectId: string,
  payload: MilestoneApprovalRequest,
): Promise<ProjectMilestonesResponse> {
  return request<ProjectMilestonesResponse>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/milestones/approve`,
    { method: 'POST', body: payload },
  );
}

export async function createDevelopmentMilestone(
  projectId: string,
  payload: DevelopmentMilestoneCreateRequest,
): Promise<DevelopmentMilestone> {
  return request<DevelopmentMilestone>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/development-milestones`,
    { method: 'POST', body: payload },
  );
}

export async function updateDevelopmentMilestone(
  projectId: string,
  devMilestoneId: string,
  payload: DevelopmentMilestoneUpdateRequest,
): Promise<DevelopmentMilestone> {
  return request<DevelopmentMilestone>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/development-milestones/${encodeURIComponent(devMilestoneId)}`,
    { method: 'PATCH', body: payload },
  );
}

// ---------------------------------------------------------------------------
// Analyses & one-time notifications
// ---------------------------------------------------------------------------

export async function triggerAnalysis(
  projectId: string,
  payload: TriggerAnalysisRequest,
): Promise<AnalysisRun> {
  return request<AnalysisRun>(`/api/v1/projects/${encodeURIComponent(projectId)}/analyses`, {
    method: 'POST',
    body: payload,
  });
}

export async function listAnalyses(projectId: string): Promise<AnalysisRun[]> {
  return request<AnalysisRun[]>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/analyses`,
  );
}

export async function getAnalysis(
  projectId: string,
  analysisRunId: string,
): Promise<AnalysisRun> {
  return request<AnalysisRun>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/analyses/${encodeURIComponent(analysisRunId)}`,
  );
}

// ---------------------------------------------------------------------------
// Scorecard, overrides & evidence
// ---------------------------------------------------------------------------

export async function fetchScorecard(
  projectId: string,
  analysisRunId?: string,
): Promise<ScorecardResponse> {
  return request<ScorecardResponse>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/scorecard`,
    { query: analysisRunId ? { analysis_run_id: analysisRunId } : undefined },
  );
}

export async function overrideCriterionScore(
  projectId: string,
  criterionAssessmentId: string,
  payload: ScoreOverrideRequest,
): Promise<CriterionAssessment> {
  return request<CriterionAssessment>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/scorecard/${encodeURIComponent(criterionAssessmentId)}`,
    { method: 'PATCH', body: payload },
  );
}

export async function fetchEvidence(
  projectId: string,
  filters?: { evidence_type?: string; analysis_run_id?: string },
): Promise<EvidenceItem[]> {
  return request<EvidenceItem[]>(`/api/v1/projects/${encodeURIComponent(projectId)}/evidence`, {
    query: filters as RequestOptions['query'],
  });
}

// ---------------------------------------------------------------------------
// Recommendations, diary, security, deployments
// ---------------------------------------------------------------------------

export async function fetchRecommendations(projectId: string): Promise<Recommendation[]> {
  return request<Recommendation[]>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/recommendations`,
  );
}

export async function fetchDiary(projectId: string): Promise<DiarySnapshot> {
  return request<DiarySnapshot>(`/api/v1/projects/${encodeURIComponent(projectId)}/diary`);
}

export async function fetchSecurityReport(projectId: string): Promise<SecurityReport> {
  return request<SecurityReport>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/security`,
  );
}

export async function fetchDeployments(projectId: string): Promise<DeploymentCheck[]> {
  return request<DeploymentCheck[]>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/deployments`,
  );
}

export async function triggerDeploymentCheck(
  projectId: string,
  payload?: DeploymentCheckTriggerRequest,
): Promise<DeploymentCheck> {
  return request<DeploymentCheck>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/deployments/check`,
    { method: 'POST', body: payload ?? {} },
  );
}

// ---------------------------------------------------------------------------
// On-call diagnostics (Phase 4, read-only)
// ---------------------------------------------------------------------------

export async function diagnoseOnCall(
  payload: OnCallDiagnoseRequest,
): Promise<OnCallDiagnosisResponse> {
  return request<OnCallDiagnosisResponse>('/api/v1/oncall/diagnose', {
    method: 'POST',
    body: payload,
  });
}

export type { AssessmentMilestone };
