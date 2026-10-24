import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import type { ProjectDetail, ProjectStatus } from '../types/api';
import { deleteProject, updateProject, ApiError } from '../api/client';
import { AdvisoryBanner } from './badges';

const STATUS_OPTIONS: ProjectStatus[] = ['active', 'paused', 'archived', 'completed'];

/**
 * Project settings — wires the existing `PATCH /api/v1/projects/{id}` and
 * `DELETE /api/v1/projects/{id}` contract surfaces via `api/client.ts`.
 * DevTrack AI stays read-only toward the *repository*; these controls edit
 * only DevTrack's own tracking metadata.
 */
export function ProjectSettingsPanel({
  project,
  onUpdated,
}: {
  project: ProjectDetail;
  onUpdated: (updated: ProjectDetail) => void;
}): JSX.Element {
  const navigate = useNavigate();
  const [status, setStatus] = useState<ProjectStatus>(project.status);
  const [startDate, setStartDate] = useState(project.start_date ?? '');
  const [targetDate, setTargetDate] = useState(project.target_date ?? '');
  const [weeklyHours, setWeeklyHours] = useState(
    project.weekly_hours != null ? String(project.weekly_hours) : '',
  );
  const [diaryPath, setDiaryPath] = useState(project.diary_path ?? '');
  const [deploymentUrl, setDeploymentUrl] = useState(project.deployment_url ?? '');
  const [schedule, setSchedule] = useState(project.daily_schedule_cron ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function handleSave(event: FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);
    setSaved(false);
    const hours = weeklyHours.trim() === '' ? null : Number(weeklyHours);
    if (hours != null && (!Number.isInteger(hours) || hours < 1 || hours > 100)) {
      setError('Weekly hours must be an integer between 1 and 100 (or blank).');
      return;
    }
    setSaving(true);
    try {
      const updated = await updateProject(project.id, {
        status,
        start_date: startDate || null,
        target_date: targetDate || null,
        weekly_hours: hours,
        diary_path: diaryPath.trim() || null,
        deployment_url: deploymentUrl.trim() || null,
        daily_schedule_cron: schedule.trim() || null,
      });
      onUpdated(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Settings update failed.');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(): Promise<void> {
    setError(null);
    setDeleting(true);
    try {
      await deleteProject(project.id);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Project deletion failed.');
      setConfirmingDelete(false);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <section aria-label="Project settings" className="stack">
      <AdvisoryBanner detail="Settings edit DevTrack tracking metadata only. DevTrack AI never pushes commits, opens pull requests, or modifies your repository." />
      <form className="card stack" onSubmit={(e) => void handleSave(e)}>
        <h2>Project settings</h2>
        <div className="filter-row">
          <label>
            Status
            <select value={status} onChange={(e) => setStatus(e.target.value as ProjectStatus)}>
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label>
            Weekly hours
            <input
              type="number"
              min={1}
              max={100}
              value={weeklyHours}
              onChange={(e) => setWeeklyHours(e.target.value)}
              placeholder="10"
            />
          </label>
        </div>
        <div className="filter-row">
          <label>
            Start date
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>
          <label>
            Target date
            <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
          </label>
        </div>
        <label>
          Diary path override
          <input
            value={diaryPath}
            onChange={(e) => setDiaryPath(e.target.value)}
            placeholder="docs/DIARY.md"
          />
        </label>
        <label>
          Deployment URL override
          <input
            value={deploymentUrl}
            onChange={(e) => setDeploymentUrl(e.target.value)}
            placeholder="https://example.com"
            inputMode="url"
          />
        </label>
        <label>
          Daily schedule (cron)
          <input
            value={schedule}
            onChange={(e) => setSchedule(e.target.value)}
            placeholder="0 6 * * *"
          />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {saved && (
          <p className="success" role="status">
            Settings saved.
          </p>
        )}
        <div className="modal-actions">
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Saving…' : 'Save settings'}
          </button>
        </div>
      </form>

      <div className="card stack danger-zone">
        <h2>Danger zone</h2>
        <p className="muted small">
          Deleting this project removes it and all associated snapshots from DevTrack. Your GitHub
          repository is never touched.
        </p>
        {!confirmingDelete ? (
          <button className="btn btn-danger" onClick={() => setConfirmingDelete(true)}>
            Delete project…
          </button>
        ) : (
          <div className="stack">
            <p role="alert">
              <strong>Delete “{project.name}” permanently?</strong> This cannot be undone.
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setConfirmingDelete(false)}
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={() => void handleDelete()}
                disabled={deleting}
              >
                {deleting ? 'Deleting…' : 'Yes, delete project'}
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
