import { useCallback, useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import type {
  AnalysisRun,
  CriterionAssessment,
  DeploymentCheck,
  DiarySnapshot,
  EvidenceItem,
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
  getAnalysis,
  listAnalyses,
  triggerDeploymentCheck,
  ApiError,
} from '../api/client';
import { useProject } from '../hooks/useProject';
import { AdvisoryBanner, DeploymentBadge, SecurityBadge } from '../components/badges';
import { MilestonesPanel } from '../components/MilestonesPanel';
import { ScorecardPanel } from '../components/ScorecardPanel';
import { MentorPanel } from '../components/MentorPanel';
import { DeploymentsPanel, DiaryPanel, EvidenceExplorer, SecurityPanel } from '../components/InfoPanels';
import { TriggerAnalysisModal } from '../components/TriggerAnalysisModal';
import { ProjectSettingsPanel } from '../components/ProjectSettingsPanel';
import { OnCallPanel } from '../components/OnCallPanel';

type Tab =
  | 'scorecard'
  | 'milestones'
  | 'mentor'
  | 'evidence'
  | 'diary'
  | 'security'
  | 'deployments'
  | 'oncall'
  | 'settings';

const TABS: { id: Tab; label: string }[] = [
  { id: 'scorecard', label: 'Scorecard' },
  { id: 'milestones', label: 'Milestones' },
  { id: 'mentor', label: 'Mentor' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'diary', label: 'Diary' },
  { id: 'security', label: 'Security' },
  { id: 'deployments', label: 'Deployment' },
  { id: 'oncall', label: 'On-Call' },
  { id: 'settings', label: 'Settings' },
];

export function ProjectDetailPage(): JSX.Element {
  const { projectId = '' } = useParams();
  const { project, setProject, loading: projectLoading, error: projectError, reload: reloadProject } =
    useProject(projectId);
  const [scorecard, setScorecard] = useState<ScorecardResponse | null>(null);
  const [milestones, setMilestones] = useState<ProjectMilestonesResponse | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [diary, setDiary] = useState<DiarySnapshot | null>(null);
  const [security, setSecurity] = useState<SecurityReport | null>(null);
  const [deployments, setDeployments] = useState<DeploymentCheck[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>('latest');
  const [selectedRun, setSelectedRun] = useState<AnalysisRun | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [tab, setTab] = useState<Tab>('scorecard');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showTrigger, setShowTrigger] = useState(false);
  const [checkingDeploy, setCheckingDeploy] = useState(false);
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const tabParam = searchParams.get('tab') as Tab | null;
    if (tabParam && TABS.some((t) => t.id === tabParam)) {
      setTab(tabParam);
    }
    if (searchParams.get('trigger') === 'open') {
      setShowTrigger(true);
    } else if (searchParams.get('trigger') === 'close') {
      setShowTrigger(false);
    }
  }, [searchParams]);

  const load = useCallback(
    async (silent = false) => {
      if (!projectId) return;
      if (!silent) setLoading(true);
      setError(null);
      try {
        const [sc, ms, recs, diarySnap, sec, deps, runs] = await Promise.all([
          fetchScorecard(projectId, selectedRunId === 'latest' ? undefined : selectedRunId).catch(
            () => null,
          ),
          fetchMilestones(projectId).catch(() => null),
          fetchRecommendations(projectId).catch(() => [] as Recommendation[]),
          fetchDiary(projectId).catch(() => null),
          fetchSecurityReport(projectId).catch(() => null),
          fetchDeployments(projectId).catch(() => [] as DeploymentCheck[]),
          listAnalyses(projectId).catch(() => [] as AnalysisRun[]),
        ]);
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
        if (selectedRunId !== 'latest') {
          const detail = await getAnalysis(projectId, selectedRunId).catch(() => null);
          setSelectedRun(detail);
        } else {
          setSelectedRun(null);
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Failed to load project.');
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [projectId, selectedRunId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const latestRun = analyses[0];
    const isPending = latestRun?.status === 'queued' || latestRun?.status === 'running';
    if (!isPending) return;

    const intervalId = window.setInterval(() => {
      void load(true);
      reloadProject();
    }, 4000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [analyses, load, reloadProject]);

  async function handleSelectRun(runId: string): Promise<void> {
    setSelectedRunId(runId);
    if (runId === 'latest' || !projectId) return;
    setHistoryLoading(true);
    setError(null);
    try {
      const [sc, detail] = await Promise.all([
        fetchScorecard(projectId, runId),
        getAnalysis(projectId, runId),
      ]);
      setScorecard(sc);
      setSelectedRun(detail);
      const fetchedEvidence = await fetchEvidence(projectId, {
        analysis_run_id: runId,
      }).catch(() => [] as EvidenceItem[]);
      setEvidence(fetchedEvidence);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load analysis run.');
    } finally {
      setHistoryLoading(false);
    }
  }

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

  function handleRefreshAll(): void {
    reloadProject();
    void load();
  }

  if (!project && (projectLoading || loading)) {
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
          {projectError ?? error ?? 'Project not found.'}
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
          <button className="btn btn-secondary" onClick={handleRefreshAll}>
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

      <section className="card" aria-label="Analysis history">
        <h2>Analysis history</h2>
        {analyses.length === 0 ? (
          <p className="muted">No runs recorded.</p>
        ) : (
          <>
            <label>
              View scorecard & evidence for run
              <select
                value={selectedRunId}
                onChange={(e) => void handleSelectRun(e.target.value)}
                aria-label="Select analysis run"
              >
                <option value="latest">Latest (default)</option>
                {analyses.map((run) => (
                  <option key={run.id} value={run.id}>
                    {run.commit_sha?.slice(0, 8) ?? run.id.slice(0, 8)} · {run.status} ·{' '}
                    {run.created_at}
                  </option>
                ))}
              </select>
            </label>
            {historyLoading && <p aria-live="polite">Loading run…</p>}
            {selectedRun && <AnalysisRunDetail run={selectedRun} />}
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
          </>
        )}
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

      {tab === 'evidence' && (
        <EvidenceExplorer projectId={projectId} initialItems={evidence} runs={analyses} />
      )}
      {tab === 'diary' && (
        <DiaryPanel
          diary={diary}
          summaryMarkdown={
            selectedRun?.summary_markdown ??
            analyses[0]?.summary_markdown ??
            project.latest_summary_markdown
          }
        />
      )}
      {tab === 'security' && <SecurityPanel report={security} />}
      {tab === 'deployments' && (
        <DeploymentsPanel
          checks={deployments}
          onCheckNow={() => void handleDeploymentCheck()}
          checking={checkingDeploy}
        />
      )}
      {tab === 'oncall' && (
        <OnCallPanel defaultContextNotes={`Project ${project.name} (${project.id})`} />
      )}
      {tab === 'settings' && (
        <ProjectSettingsPanel project={project} onUpdated={(updated) => setProject(updated)} />
      )}

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

function AnalysisRunDetail({ run }: { run: AnalysisRun }): JSX.Element {
  return (
    <article className="card analysis-detail" aria-label="Selected analysis run detail">
      <header className="card-header">
        <h3>
          Run <code>{run.id.slice(0, 8)}</code> — {run.trigger_type} · {run.status}
        </h3>
        <span className={`badge status-${run.status}`}>{run.status}</span>
      </header>
      <dl className="card-meta">
        <div>
          <dt>Commit SHA</dt>
          <dd>
            <code>{run.commit_sha ?? '—'}</code>
          </dd>
        </div>
        <div>
          <dt>Previous SHA</dt>
          <dd>
            <code>{run.previous_commit_sha?.slice(0, 8) ?? '—'}</code>
          </dd>
        </div>
        <div>
          <dt>Scores (est / ver / max)</dt>
          <dd>
            {run.estimated_total_points} / {run.verified_total_points} / {run.max_total_points}
          </dd>
        </div>
        <div>
          <dt>Dev completion</dt>
          <dd>{run.dev_completion_pct.toFixed(1)}%</dd>
        </div>
        <div>
          <dt>Flags</dt>
          <dd>
            {run.stalled_flag ? 'stalled' : '—'}
            {run.scope_creep_flag ? ' · scope-creep' : ''}
          </dd>
        </div>
      </dl>
      {run.summary_markdown && (
        <details className="levels" open>
          <summary>Run summary</summary>
          <pre className="snippet snippet-full" tabIndex={0}>
            {run.summary_markdown}
          </pre>
        </details>
      )}
      {run.error_message && (
        <p className="error small" role="alert">
          {run.error_message}
        </p>
      )}
      <p className="muted small">
        Started {run.started_at ?? '—'} · completed {run.completed_at ?? '—'}
        {run.ephemeral_notification_queued ? ' · one-time email queued (volatile only)' : ''}.
      </p>
    </article>
  );
}
