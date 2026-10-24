import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import type {
  AnalysisRun,
  CriterionAssessment,
  DeploymentCheck,
  DiarySnapshot,
  EvidenceItem,
  ProjectDetail,
  ProjectMilestonesResponse,
  Recommendation,
  ScorecardResponse,
  SecurityReport,
} from '../types/api';
import {
  fetchDiary,
  fetchDeployments,
  fetchEvidence,
  fetchMilestones,
  fetchRecommendations,
  fetchScorecard,
  fetchSecurityReport,
  getProject,
  listAnalyses,
  triggerDeploymentCheck,
  ApiError,
} from '../api/client';
import { AdvisoryBanner, DeploymentBadge, SecurityBadge } from '../components/badges';
import { MilestonesPanel } from '../components/MilestonesPanel';
import { ScorecardPanel } from '../components/ScorecardPanel';
import { MentorPanel } from '../components/MentorPanel';
import { DeploymentsPanel, DiaryPanel, EvidencePanel, SecurityPanel } from '../components/InfoPanels';
import { TriggerAnalysisModal } from '../components/TriggerAnalysisModal';

type Tab = 'scorecard' | 'milestones' | 'mentor' | 'evidence' | 'diary' | 'security' | 'deployments';

const TABS: { id: Tab; label: string }[] = [
  { id: 'scorecard', label: 'Scorecard' },
  { id: 'milestones', label: 'Milestones' },
  { id: 'mentor', label: 'Mentor' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'diary', label: 'Diary' },
  { id: 'security', label: 'Security' },
  { id: 'deployments', label: 'Deployment' },
];

export function ProjectDetailPage(): JSX.Element {
  const { projectId = '' } = useParams();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [scorecard, setScorecard] = useState<ScorecardResponse | null>(null);
  const [milestones, setMilestones] = useState<ProjectMilestonesResponse | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [diary, setDiary] = useState<DiarySnapshot | null>(null);
  const [security, setSecurity] = useState<SecurityReport | null>(null);
  const [deployments, setDeployments] = useState<DeploymentCheck[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisRun[]>([]);
  const [tab, setTab] = useState<Tab>('scorecard');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showTrigger, setShowTrigger] = useState(false);
  const [checkingDeploy, setCheckingDeploy] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [proj, sc, ms, recs, diarySnap, sec, deps, runs] = await Promise.all([
        getProject(projectId),
        fetchScorecard(projectId).catch(() => null),
        fetchMilestones(projectId).catch(() => null),
        fetchRecommendations(projectId).catch(() => [] as Recommendation[]),
        fetchDiary(projectId).catch(() => null),
        fetchSecurityReport(projectId).catch(() => null),
        fetchDeployments(projectId).catch(() => [] as DeploymentCheck[]),
        listAnalyses(projectId).catch(() => [] as AnalysisRun[]),
      ]);
      setProject(proj);
      setScorecard(sc);
      setMilestones(ms);
      setRecommendations(recs);
      setDiary(diarySnap);
      setSecurity(sec);
      setDeployments(deps);
      setAnalyses(runs);
      if (sc) {
        const fetchedEvidence = await fetchEvidence(projectId).catch(() => [] as EvidenceItem[]);
        setEvidence(fetchedEvidence);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load project.');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  function handleScorecardUpdate(updated: CriterionAssessment): void {
    setScorecard((prev) =>
      prev == null
        ? prev
        : {
            ...prev,
            criteria_assessments: prev.criteria_assessments.map((c) =>
              c.id === updated.id ? updated : c,
            ),
          },
    );
  }

  async function handleDeploymentCheck(): Promise<void> {
    setCheckingDeploy(true);
    try {
      const check = await triggerDeploymentCheck(projectId);
      setDeployments((prev) => [check, ...prev]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Deployment check failed.');
    } finally {
      setCheckingDeploy(false);
    }
  }

  if (loading) {
    return (
      <main className="page">
        <p aria-live="polite">Loading project…</p>
      </main>
    );
  }

  if (!project) {
    return (
      <main className="page">
        <p className="error" role="alert">
          {error ?? 'Project not found.'}
        </p>
      </main>
    );
  }

  const dev = project.development_progress;
  const score = project.expected_score;

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <h1>{project.name}</h1>
          <p className="muted">
            {project.github_repo_url} · target {project.target_date ?? '—'} · last SHA{' '}
            <code>{project.last_commit_sha?.slice(0, 8) ?? '—'}</code>
          </p>
        </div>
        <div className="page-actions">
          <button className="btn btn-secondary" onClick={() => void load()}>
            Refresh
          </button>
          <button className="btn btn-primary" onClick={() => setShowTrigger(true)}>
            Run analysis
          </button>
        </div>
      </header>

      <AdvisoryBanner />

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <section className="card headline-grid" aria-label="Project headline metrics">
        <div className="metric">
          <span className="metric-label">Development Progress (tasks)</span>
          <span className="metric-value">{dev.completion_pct.toFixed(1)}%</span>
          <span className="muted small">
            {dev.completed_tasks}/{dev.total_tasks} completed
          </span>
        </div>
        <div className="metric">
          <span className="metric-label">Expected Course Score (advisory, X/24)</span>
          <span className="metric-value">
            {score.effective_points}/{score.max_points}
          </span>
          <span className="muted small">
            {score.verified_points} verified · {score.estimated_points} estimated
          </span>
        </div>
        <div className="metric">
          <span className="metric-label">Status badges</span>
          <span className="badge-row">
            <SecurityBadge status={project.security_status} />
            <DeploymentBadge reachable={project.deployment_reachable} />
          </span>
        </div>
      </section>

      <nav className="tabs" aria-label="Project sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? 'tab tab-active' : 'tab'}
            onClick={() => setTab(t.id)}
            aria-selected={tab === t.id}
            role="tab"
          >
            {t.label}
          </button>
        ))}
      </nav>

      {tab === 'scorecard' &&
        (scorecard ? (
          <ScorecardPanel
            projectId={projectId}
            assessments={scorecard.criteria_assessments}
            disclaimer={scorecard.advisory_disclaimer}
            onUpdated={handleScorecardUpdate}
          />
        ) : (
          <p className="muted">No scorecard yet — run an analysis first.</p>
        ))}

      {tab === 'milestones' &&
        (milestones ? (
          <MilestonesPanel projectId={projectId} milestones={milestones} onRefresh={() => void load()} />
        ) : (
          <p className="muted">No milestones yet.</p>
        ))}

      {tab === 'mentor' && (
        <MentorPanel
          recommendations={recommendations}
          stalled={project.stalled_flag}
          scopeCreep={project.scope_creep_flag}
        />
      )}

      {tab === 'evidence' && <EvidencePanel items={evidence} />}
      {tab === 'diary' && <DiaryPanel diary={diary} />}
      {tab === 'security' && <SecurityPanel report={security} />}
      {tab === 'deployments' && (
        <DeploymentsPanel
          checks={deployments}
          onCheckNow={() => void handleDeploymentCheck()}
          checking={checkingDeploy}
        />
      )}

      <section className="card" aria-label="Analysis history">
        <h2>Analysis runs</h2>
        {analyses.length === 0 ? (
          <p className="muted">No runs recorded.</p>
        ) : (
          <ul className="run-list">
            {analyses.map((run) => (
              <li key={run.id}>
                <code>{run.commit_sha?.slice(0, 8) ?? '—'}</code> · {run.status} · est{' '}
                {run.estimated_total_points} / ver {run.verified_total_points} / max{' '}
                {run.max_total_points} · dev {run.dev_completion_pct.toFixed(1)}%
                {run.stalled_flag && ' · stalled'}
                {run.scope_creep_flag && ' · scope-creep'}
              </li>
            ))}
          </ul>
        )}
      </section>

      {showTrigger && (
        <TriggerAnalysisModal
          projectId={projectId}
          projectName={project.name}
          onClose={() => setShowTrigger(false)}
          onTriggered={() => void load()}
        />
      )}
    </main>
  );
}
