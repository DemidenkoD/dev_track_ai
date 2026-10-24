import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { fetchDashboard, listRubrics, createProject, isAllowedGitHubRepoUrl, ApiError } from '../api/client';
import type { DashboardOverview, RubricSummary } from '../types/api';
import { ProjectCard } from '../components/ProjectCard';
import { AdvisoryBanner } from '../components/badges';

export function DashboardPage(): JSX.Element {
  const [dashboard, setDashboard] = useState<DashboardOverview | null>(null);
  const [rubrics, setRubrics] = useState<RubricSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [dash, rubricList] = await Promise.all([fetchDashboard(), listRubrics()]);
      setDashboard(dash);
      setRubrics(rubricList);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load dashboard.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

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
          <button className="btn btn-secondary" onClick={() => void load()}>
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

      {showCreate && <CreateProjectForm rubrics={rubrics} onCreated={() => { setShowCreate(false); void load(); }} />}

      <div className="project-grid">
        {(dashboard?.projects ?? []).map((project) => (
          <ProjectCard key={project.id} project={project} />
        ))}
      </div>
      {dashboard && dashboard.projects.length === 0 && (
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
  const [githubRepoUrl, setGithubRepoUrl] = useState('');
  const [rubricId, setRubricId] = useState(rubrics[0]?.id ?? '');
  const [targetDate, setTargetDate] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);
    if (!isAllowedGitHubRepoUrl(githubRepoUrl)) {
      setError('Only public GitHub repository URLs (https://github.com/<owner>/<repo>) are permitted.');
      return;
    }
    setSaving(true);
    try {
      await createProject({
        name: name.trim(),
        github_repo_url: githubRepoUrl.trim(),
        rubric_id: rubricId || null,
        target_date: targetDate || null,
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
      <label>
        Project name
        <input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />
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
      <label>
        Target date
        <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
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
