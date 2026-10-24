import { useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { createProject, isAllowedGitHubRepoUrl, listProjects, ApiError } from '../api/client';
import type { ProjectStatus, ProjectSummary, RubricSummary } from '../types/api';
import { useDashboard } from '../hooks/useDashboard';
import { ProjectCard } from '../components/ProjectCard';
import { AdvisoryBanner } from '../components/badges';

const STATUS_FILTERS: Array<'' | ProjectStatus> = ['', 'active', 'paused', 'archived', 'completed'];

export function DashboardPage(): JSX.Element {
  const { dashboard, rubrics, health, loading, error, reload } = useDashboard();
  const [showCreate, setShowCreate] = useState(false);
  const [statusFilter, setStatusFilter] = useState<'' | ProjectStatus>('');
  const [filteredProjects, setFilteredProjects] = useState<ProjectSummary[] | null>(null);
  const [filterLoading, setFilterLoading] = useState(false);
  const [filterError, setFilterError] = useState<string | null>(null);

  useEffect(() => {
    if (statusFilter === '') {
      setFilteredProjects(null);
      setFilterError(null);
      return;
    }
    let cancelled = false;
    setFilterLoading(true);
    setFilterError(null);
    listProjects(statusFilter)
      .then((projects) => {
        if (!cancelled) setFilteredProjects(projects);
      })
      .catch((err) => {
        if (!cancelled) {
          setFilterError(err instanceof ApiError ? err.message : 'Status filter failed.');
        }
      })
      .finally(() => {
        if (!cancelled) setFilterLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [statusFilter]);

  const projects = useMemo(
    () => filteredProjects ?? dashboard?.projects ?? [],
    [filteredProjects, dashboard],
  );

  const aggregates = useMemo(() => {
    // Client-side aggregates derived strictly from contract `projects` data
    // (used unless the backend starts providing server-side `totals`).
    const source = dashboard?.projects ?? [];
    const estimated = source.reduce((sum, p) => sum + p.expected_score.estimated_points, 0);
    const verified = source.reduce((sum, p) => sum + p.expected_score.verified_points, 0);
    const effective = source.reduce((sum, p) => sum + p.expected_score.effective_points, 0);
    const max = source.reduce((sum, p) => sum + p.expected_score.max_points, 0);
    const meeting = source.filter((p) => p.expected_score.meets_passing_threshold).length;
    const deadlines = (dashboard?.upcoming_deadlines ??
      source
        .filter((p) => p.target_date != null)
        .map((p) => ({
          project_id: p.id,
          project_name: p.name,
          target_date: p.target_date as string,
          status: p.status,
        }))
    )
      .slice()
      .sort((a, b) => a.target_date.localeCompare(b.target_date))
      .slice(0, 5);
    return {
      estimated,
      verified,
      effective,
      max,
      meeting,
      total: source.length,
      deadlines,
      serverTotals: dashboard?.totals ?? null,
    };
  }, [dashboard]);

  if (loading) {
    return (
      <main className="page">
        <p aria-live="polite">Loading dashboard…</p>
      </main>
    );
  }

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <h1>Project Dashboard</h1>
          <p className="muted">
            {dashboard?.active_projects ?? 0} active of {dashboard?.total_projects ?? 0} tracked
            projects.
          </p>
        </div>
        <div className="page-actions">
          <label className="muted small">
            Status filter{' '}
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as '' | ProjectStatus)}
              aria-label="Filter projects by status"
            >
              <option value="">All (dashboard)</option>
              {STATUS_FILTERS.filter((s) => s !== '').map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <button className="btn btn-secondary" onClick={reload}>
            Refresh
          </button>
          <button className="btn btn-primary" onClick={() => setShowCreate((v) => !v)}>
            {showCreate ? 'Close' : 'New project'}
          </button>
        </div>
      </header>

      <AdvisoryBanner />

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <section className="card" aria-label="Portfolio aggregates">
        <div className="headline-grid">
          <div className="metric">
            <span className="metric-label">Portfolio Expected Score (advisory)</span>
            <span className="metric-value">
              {aggregates.serverTotals?.effective_points ?? aggregates.effective}/
              {aggregates.serverTotals?.max_points ?? aggregates.max}
            </span>
            <span className="muted small">
              {aggregates.serverTotals?.verified_points ?? aggregates.verified} verified ·{' '}
              {aggregates.serverTotals?.estimated_points ?? aggregates.estimated} estimated
              {aggregates.serverTotals != null && ' (server totals)'}
            </span>
          </div>
          <div className="metric">
            <span className="metric-label">Passing threshold</span>
            <span className="metric-value">
              {aggregates.meeting}/{aggregates.total}
            </span>
            <span className="muted small">projects meet their rubric pass threshold</span>
          </div>
          <div className="metric">
            <span className="metric-label">Backend health</span>
            <span className="badge-row">
              {health ? (
                <>
                  <span className="badge badge-verified">API: {health.status}</span>
                  <span className="badge badge-unknown">DB: {health.database}</span>
                  <span className="badge badge-unknown">Worker: {health.worker_status}</span>
                </>
              ) : (
                <span className="badge badge-unknown">Health unavailable</span>
              )}
            </span>
            {health && <span className="muted small">version {health.version}</span>}
          </div>
        </div>
        <div>
          <h3>Upcoming deadlines</h3>
          {aggregates.deadlines.length === 0 ? (
            <p className="muted small">No target dates set.</p>
          ) : (
            <ul className="run-list">
              {aggregates.deadlines.map((d) => (
                <li key={d.project_id}>
                  <strong>{d.project_name}</strong> — target {d.target_date}{' '}
                  <span className={`badge status-${d.status}`}>{d.status}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {showCreate && (
        <CreateProjectForm
          rubrics={rubrics}
          onCreated={() => {
            setShowCreate(false);
            reload();
          }}
        />
      )}

      {filterLoading && <p aria-live="polite">Filtering projects…</p>}
      {filterError && (
        <p className="error" role="alert">
          {filterError}
        </p>
      )}
      {statusFilter !== '' && (
        <p className="muted small" aria-live="polite">
          Showing {projects.length} project(s) with status “{statusFilter}” (via{' '}
          <code>GET /api/v1/projects?status=</code>).
        </p>
      )}

      <div className="project-grid">
        {projects.map((project) => (
          <ProjectCard key={project.id} project={project} />
        ))}
      </div>
      {projects.length === 0 && (
        <p className="muted">No projects yet — create one to start tracking.</p>
      )}
    </main>
  );
}

function CreateProjectForm({
  rubrics,
  onCreated,
}: {
  rubrics: RubricSummary[];
  onCreated: () => void;
}): JSX.Element {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [courseName, setCourseName] = useState('AI Dev Tools Zoomcamp 2026');
  const [githubRepoUrl, setGithubRepoUrl] = useState('');
  const [rubricId, setRubricId] = useState(rubrics[0]?.id ?? '');
  const [startDate, setStartDate] = useState('');
  const [targetDate, setTargetDate] = useState('');
  const [weeklyHours, setWeeklyHours] = useState('12');
  const [diaryPath, setDiaryPath] = useState('');
  const [deploymentUrl, setDeploymentUrl] = useState('');
  const [schedule, setSchedule] = useState('0 6 * * *');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);
    if (!isAllowedGitHubRepoUrl(githubRepoUrl)) {
      setError('Only public GitHub repository URLs (https://github.com/<owner>/<repo>) are permitted.');
      return;
    }
    const hours = weeklyHours.trim() === '' ? undefined : Number(weeklyHours);
    if (hours !== undefined && (!Number.isInteger(hours) || hours < 1 || hours > 100)) {
      setError('Weekly hours must be an integer between 1 and 100.');
      return;
    }
    setSaving(true);
    try {
      await createProject({
        name: name.trim(),
        description: description.trim() || null,
        github_repo_url: githubRepoUrl.trim(),
        course_name: courseName.trim() || undefined,
        rubric_id: rubricId || null,
        start_date: startDate || null,
        target_date: targetDate || null,
        weekly_hours: hours,
        diary_path: diaryPath.trim() || null,
        deployment_url: deploymentUrl.trim() || null,
        daily_schedule_cron: schedule.trim() || undefined,
      });
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Project creation failed.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card stack" onSubmit={(e) => void handleSubmit(e)} aria-label="Create project">
      <h2>Track a new repository</h2>
      <p className="muted small">
        DevTrack AI inspects <strong>public GitHub repositories only</strong> and is read-only — it
        never pushes commits or opens pull requests.
      </p>
      <div className="filter-row">
        <label>
          Project name
          <input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />
        </label>
        <label>
          Course name
          <input value={courseName} onChange={(e) => setCourseName(e.target.value)} />
        </label>
      </div>
      <label>
        Description (optional)
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
      </label>
      <label>
        Public GitHub URL
        <input
          value={githubRepoUrl}
          onChange={(e) => setGithubRepoUrl(e.target.value)}
          placeholder="https://github.com/<owner>/<repo>"
          inputMode="url"
          required
        />
      </label>
      <label>
        Rubric
        <select value={rubricId} onChange={(e) => setRubricId(e.target.value)}>
          {rubrics.map((r) => (
            <option key={r.id} value={r.id}>
              {r.title} ({r.version}, max {r.max_points})
            </option>
          ))}
        </select>
      </label>
      <div className="filter-row">
        <label>
          Start date
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </label>
        <label>
          Target date
          <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
        </label>
        <label>
          Weekly hours
          <input
            type="number"
            min={1}
            max={100}
            value={weeklyHours}
            onChange={(e) => setWeeklyHours(e.target.value)}
          />
        </label>
      </div>
      <div className="filter-row">
        <label>
          Diary path (optional)
          <input
            value={diaryPath}
            onChange={(e) => setDiaryPath(e.target.value)}
            placeholder="docs/DIARY.md"
          />
        </label>
        <label>
          Deployment URL (optional)
          <input
            value={deploymentUrl}
            onChange={(e) => setDeploymentUrl(e.target.value)}
            placeholder="https://example.com"
            inputMode="url"
          />
        </label>
      </div>
      <label>
        Daily schedule (cron)
        <input value={schedule} onChange={(e) => setSchedule(e.target.value)} placeholder="0 6 * * *" />
      </label>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button type="submit" className="btn btn-primary" disabled={saving}>
        {saving ? 'Creating…' : 'Create project'}
      </button>
    </form>
  );
}
