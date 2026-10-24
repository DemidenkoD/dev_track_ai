import type { Recommendation } from '../types/api';

const PRIORITY_CLASS: Record<string, string> = {
  critical: 'badge badge-critical',
  high: 'badge badge-needs-review',
  medium: 'badge badge-estimated',
  low: 'badge badge-unknown',
};

/**
 * Mentor + recommendations: high-ROI list with points delta, effort, risk.
 * Detects/surfaces stalled + scope-creep alerts passed in from analysis runs.
 */
export function MentorPanel({
  recommendations,
  stalled,
  scopeCreep,
}: {
  recommendations: Recommendation[];
  stalled: boolean;
  scopeCreep: boolean;
}): JSX.Element {
  const sorted = [...recommendations].sort((a, b) => a.rank - b.rank);
  return (
    <section aria-label="Mentor recommendations">
      {(stalled || scopeCreep) && (
        <div className="alert-row">
          {stalled && (
            <p className="alert alert-stalled" role="alert">
              ⚠ Stalled development detected — no meaningful progress since the previous commit
              snapshot. Consider the top recommendation below.
            </p>
          )}
          {scopeCreep && (
            <p className="alert alert-creep" role="alert">
              ⚠ Scope-creep signal — recent changes drift from approved milestones. Re-check the
              Development tab before adding new work.
            </p>
          )}
        </div>
      )}
      {sorted.length === 0 && (
        <p className="muted">No recommendations yet — run an analysis to get mentor guidance.</p>
      )}
      <ol className="rec-list">
        {sorted.map((rec) => (
          <li key={rec.id} className="card rec-card">
            <header className="card-header">
              <strong>
                #{rec.rank} {rec.suggested_task}
              </strong>
              <span className={PRIORITY_CLASS[rec.priority] ?? 'badge badge-unknown'}>
                {rec.priority}
              </span>
            </header>
            <p>{rec.rationale}</p>
            <p className="muted small">
              Criterion <code>{rec.related_criterion_code}</code> · potential{' '}
              <strong>+{rec.potential_points_delta} pts (advisory)</strong> · effort{' '}
              {rec.estimated_effort_hours != null ? `~${rec.estimated_effort_hours}h` : 'n/a'} ·
              risk {rec.technical_risk}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}
