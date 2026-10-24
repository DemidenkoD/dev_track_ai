import { useState } from 'react';
import type { FormEvent } from 'react';
import type { DevelopmentMilestoneStatus, ProjectMilestonesResponse } from '../types/api';
import { approveMilestones, createDevelopmentMilestone, updateDevelopmentMilestone, ApiError } from '../api/client';

const DEV_STATUS_LABEL: Record<DevelopmentMilestoneStatus, string> = {
  outstanding: 'Outstanding',
  partial: 'Partial',
  completed: 'Completed',
};

/**
 * Guardrail 4 — Two-level milestone view.
 * Assessment milestones (official criteria + approval banner) are rendered
 * separately from development milestones (engineering tasks).
 * Completing dev tasks NEVER auto-awards assessment points in UI logic —
 * the UI states this explicitly and never derives a score from task status.
 */
export function MilestonesPanel({
  projectId,
  milestones,
  onRefresh,
}: {
  projectId: string;
  milestones: ProjectMilestonesResponse;
  onRefresh: () => void;
}): JSX.Element {
  const [tab, setTab] = useState<'assessment' | 'development'>('assessment');
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleApproveAll(): Promise<void> {
    setError(null);
    setApproving(true);
    try {
      await approveMilestones(projectId, { approve_all: true });
      onRefresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Approval failed.');
    } finally {
      setApproving(false);
    }
  }

  return (
    <section aria-label="Milestones">
      {!milestones.milestones_approved ? (
        <div className="approval-banner" role="alert">
          <p>
            <strong>Approval required:</strong> generated milestones are drafts until you approve
            them. Approval activates progress tracking only — it never awards course points.
          </p>
          <button className="btn btn-primary" onClick={() => void handleApproveAll()} disabled={approving}>
            {approving ? 'Approving…' : 'Approve all milestones'}
          </button>
          {error && <p className="error">{error}</p>}
        </div>
      ) : (
        <div className="approval-banner approval-banner-ok" role="status">
          <p>
            <strong>Milestones approved</strong> — tracking active. Development task completion does
            not award official assessment points.
          </p>
        </div>
      )}

      <div className="tabs" role="tablist" aria-label="Milestone levels">
        <button
          role="tab"
          aria-selected={tab === 'assessment'}
          className={tab === 'assessment' ? 'tab tab-active' : 'tab'}
          onClick={() => setTab('assessment')}
        >
          Assessment Milestones (official criteria)
        </button>
        <button
          role="tab"
          aria-selected={tab === 'development'}
          className={tab === 'development' ? 'tab tab-active' : 'tab'}
          onClick={() => setTab('development')}
        >
          Development Milestones (engineering tasks)
        </button>
      </div>

      {tab === 'assessment' ? (
        <div className="milestone-list">
          {milestones.assessment_milestones.map((am) => (
            <article key={am.id} className="card">
              <header className="card-header">
                <div>
                  <h3>{am.title}</h3>
                  <p className="muted small">
                    Criterion <code>{am.criterion_code}</code> · max {am.max_points} pts (official)
                    {am.target_date ? ` · target ${am.target_date}` : ''}
                  </p>
                </div>
                {am.is_approved ? (
                  <span className="badge badge-verified">Approved</span>
                ) : (
                  <span className="badge badge-needs-review">Draft</span>
                )}
              </header>
              <p className="muted small">
                Points for this criterion come only from rubric evaluation / human verification on
                the Scorecard — never from task completion below ({am.development_milestones.length}{' '}
                linked tasks).
              </p>
            </article>
          ))}
          {milestones.assessment_milestones.length === 0 && (
            <p className="muted">No assessment milestones yet.</p>
          )}
        </div>
      ) : (
        <DevelopmentTaskList
          projectId={projectId}
          milestones={milestones}
          onRefresh={onRefresh}
        />
      )}
    </section>
  );
}

function DevelopmentTaskList({
  projectId,
  milestones,
  onRefresh,
}: {
  projectId: string;
  milestones: ProjectMilestonesResponse;
  onRefresh: () => void;
}): JSX.Element {
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [showCreateFor, setShowCreateFor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleStatusChange(devId: string, status: DevelopmentMilestoneStatus): Promise<void> {
    setError(null);
    setUpdatingId(devId);
    try {
      await updateDevelopmentMilestone(projectId, devId, { status });
      onRefresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Update failed.');
    } finally {
      setUpdatingId(null);
    }
  }

  return (
    <div className="milestone-list">
      {milestones.assessment_milestones.map((am) => (
        <article key={am.id} className="card">
          <h3 className="muted small">
            Under criterion <code>{am.criterion_code}</code> — {am.title}
          </h3>
          {am.development_milestones.length === 0 && (
            <p className="muted small">No engineering tasks linked yet.</p>
          )}
          <ul className="task-list">
            {am.development_milestones.map((task) => (
              <li key={task.id} className="task-row">
                <div>
                  <strong>{task.title}</strong>
                  {task.description && <p className="muted small">{task.description}</p>}
                  <p className="muted small">
                    {task.estimated_effort_hours != null
                      ? `~${task.estimated_effort_hours}h`
                      : 'effort n/a'}
                    {task.due_date ? ` · due ${task.due_date}` : ''} · source {task.source}
                  </p>
                </div>
                <div className="task-actions">
                  <span className={`badge dev-${task.status}`}>{DEV_STATUS_LABEL[task.status]}</span>
                  <select
                    aria-label={`Update status for ${task.title}`}
                    value={task.status}
                    disabled={updatingId === task.id}
                    onChange={(e) =>
                      void handleStatusChange(task.id, e.target.value as DevelopmentMilestoneStatus)
                    }
                  >
                    <option value="outstanding">Outstanding</option>
                    <option value="partial">Partial</option>
                    <option value="completed">Completed</option>
                  </select>
                </div>
              </li>
            ))}
          </ul>
          {showCreateFor === am.id ? (
            <CreateTaskForm
              projectId={projectId}
              assessmentMilestoneId={am.id}
              onDone={() => {
                setShowCreateFor(null);
                onRefresh();
              }}
              onCancel={() => setShowCreateFor(null)}
            />
          ) : (
            <button className="btn btn-secondary" onClick={() => setShowCreateFor(am.id)}>
              Add task
            </button>
          )}
        </article>
      ))}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <p className="muted small">
        Note: marking tasks completed updates Development Progress (%) only. It never changes the
        Expected Course Score — scores change only via rubric evaluation or human override.
      </p>
    </div>
  );
}

function CreateTaskForm({
  projectId,
  assessmentMilestoneId,
  onDone,
  onCancel,
}: {
  projectId: string;
  assessmentMilestoneId: string;
  onDone: () => void;
  onCancel: () => void;
}): JSX.Element {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!title.trim()) {
      setError('Title is required.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createDevelopmentMilestone(projectId, {
        assessment_milestone_id: assessmentMilestoneId,
        title: title.trim(),
        description: description.trim() || null,
      });
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Create failed.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="override-form" onSubmit={(e) => void handleSubmit(e)}>
      <label>
        Task title
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>
      <label>
        Description
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
      </label>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="modal-actions">
        <button type="button" className="btn btn-secondary" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? 'Adding…' : 'Add task'}
        </button>
      </div>
    </form>
  );
}
