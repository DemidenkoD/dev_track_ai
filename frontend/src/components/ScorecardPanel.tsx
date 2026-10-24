import { useState } from 'react';
import type { FormEvent } from 'react';
import type { CriterionAssessment, ScoreState } from '../types/api';
import { overrideCriterionScore, ApiError } from '../api/client';
import { ScoreStateBadge, AdvisoryBanner } from './badges';

/**
 * Guardrail 2 + 3 — Scorecard with advisory disclaimer, score_state badges,
 * and human-override side-by-side view (original ai_proposed_points +
 * ai_reasoning are always preserved and displayed).
 */
export function ScorecardPanel({
  projectId,
  assessments,
  disclaimer,
  onUpdated,
}: {
  projectId: string;
  assessments: CriterionAssessment[];
  disclaimer: string;
  onUpdated: (updated: CriterionAssessment) => void;
}): JSX.Element {
  return (
    <section aria-label="Rubric scorecard">
      <AdvisoryBanner detail={disclaimer} />
      <div className="scorecard-grid">
        {assessments.map((criterion) => (
          <CriterionCard
            key={criterion.id}
            projectId={projectId}
            criterion={criterion}
            onUpdated={onUpdated}
          />
        ))}
      </div>
    </section>
  );
}

function CriterionCard({
  projectId,
  criterion,
  onUpdated,
}: {
  projectId: string;
  criterion: CriterionAssessment;
  onUpdated: (updated: CriterionAssessment) => void;
}): JSX.Element {
  const [editing, setEditing] = useState(false);
  const hasOverride = criterion.human_override_points != null;

  return (
    <article className="card criterion-card">
      <header className="card-header">
        <div>
          <h3>
            {criterion.criterion_name || criterion.criterion_code}{' '}
            <span className="muted small">({criterion.criterion_code})</span>
          </h3>
          <p className="muted small">
            Effective: <strong>{criterion.effective_points}/{criterion.max_points}</strong>
          </p>
        </div>
        <ScoreStateBadge state={criterion.score_state} />
      </header>

      <div className="side-by-side">
        <div className="side ai-side">
          <h4>AI proposal (advisory)</h4>
          <p className="score-line">
            <strong>{criterion.ai_proposed_points}/{criterion.max_points}</strong>{' '}
            <span className="muted small">confidence {(criterion.ai_confidence * 100).toFixed(0)}%</span>
          </p>
          <p>{criterion.ai_reasoning}</p>
          {criterion.missing_for_next_level && (
            <p className="muted small">Missing for next level: {criterion.missing_for_next_level}</p>
          )}
        </div>
        <div className="side human-side">
          <h4>Human review</h4>
          {hasOverride ? (
            <>
              <p className="score-line">
                <strong>
                  {criterion.human_override_points}/{criterion.max_points}
                </strong>{' '}
                <span className="muted small">
                  {criterion.overridden_at ? `overridden ${criterion.overridden_at}` : 'overridden'}
                </span>
              </p>
              <p>{criterion.human_override_reason ?? 'No reason recorded.'}</p>
            </>
          ) : (
            <p className="muted">No human override — AI estimate stands as advisory only.</p>
          )}
        </div>
      </div>

      {criterion.scoring_levels.length > 0 && (
        <details className="levels">
          <summary>Official scoring levels ({criterion.max_points} max)</summary>
          <ul>
            {criterion.scoring_levels.map((level, i) => (
              <li key={i}>
                <strong>{level.points} pts</strong> — {level.description}
              </li>
            ))}
          </ul>
        </details>
      )}

      {criterion.evidence_items.length > 0 && (
        <details className="levels">
          <summary>Linked evidence ({criterion.evidence_items.length})</summary>
          <ul>
            {criterion.evidence_items.map((ev) => (
              <li key={ev.id}>
                <span className="badge badge-unknown">{ev.evidence_type}</span> {ev.title}{' '}
                <span className="muted small">{ev.path_or_url}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {!editing ? (
        <button className="btn btn-secondary" onClick={() => setEditing(true)}>
          Verify / override
        </button>
      ) : (
        <OverrideForm
          projectId={projectId}
          criterion={criterion}
          onDone={(updated) => {
            setEditing(false);
            if (updated) onUpdated(updated);
          }}
          onCancel={() => setEditing(false)}
        />
      )}
    </article>
  );
}

function OverrideForm({
  projectId,
  criterion,
  onDone,
  onCancel,
}: {
  projectId: string;
  criterion: CriterionAssessment;
  onDone: (updated: CriterionAssessment | null) => void;
  onCancel: () => void;
}): JSX.Element {
  const [scoreState, setScoreState] = useState<ScoreState>(criterion.score_state);
  const [points, setPoints] = useState<string>(
    criterion.human_override_points != null ? String(criterion.human_override_points) : '',
  );
  const [reason, setReason] = useState<string>(criterion.human_override_reason ?? '');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);
    const parsed = points.trim() === '' ? null : Number(points);
    if (parsed != null && (!Number.isInteger(parsed) || parsed < 0 || parsed > criterion.max_points)) {
      setError(`Override points must be an integer between 0 and ${criterion.max_points}.`);
      return;
    }
    setSaving(true);
    try {
      const updated = await overrideCriterionScore(projectId, criterion.id, {
        score_state: scoreState,
        human_override_points: parsed,
        human_override_reason: reason.trim() || null,
      });
      onDone(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Override failed.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="override-form" onSubmit={(e) => void handleSubmit(e)}>
      <label>
        Score state
        <select value={scoreState} onChange={(e) => setScoreState(e.target.value as ScoreState)}>
          <option value="estimated">Estimated (advisory)</option>
          <option value="verified">Verified (human-confirmed)</option>
          <option value="needs_review">Needs Review</option>
        </select>
      </label>
      <label>
        Human override points (0–{criterion.max_points}, blank = keep AI value)
        <input
          type="number"
          min={0}
          max={criterion.max_points}
          value={points}
          onChange={(e) => setPoints(e.target.value)}
        />
      </label>
      <label>
        Human override reason
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} />
      </label>
      <p className="muted small">
        Original AI proposal ({criterion.ai_proposed_points}/{criterion.max_points}) and reasoning
        are preserved and remain visible side-by-side.
      </p>
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
          {saving ? 'Saving…' : 'Save override'}
        </button>
      </div>
    </form>
  );
}
