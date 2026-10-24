import type { ScoreState, SecurityStatus } from '../types/api';

export const ADVISORY_DISCLAIMER =
  'AI estimates are advisory and never represent an official course grade.';

export function AdvisoryBanner({ detail }: { detail?: string }): JSX.Element {
  return (
    <div className="advisory-banner" role="note" aria-label="Advisory disclaimer">
      <span className="advisory-banner-icon" aria-hidden="true">
        ⚠
      </span>
      <p>
        <strong>Advisory only:</strong> {detail ?? ADVISORY_DISCLAIMER} DevTrack AI is read-only —
        it never pushes commits, opens pull requests, or modifies your repositories.
      </p>
    </div>
  );
}

const SCORE_STATE_META: Record<ScoreState, { label: string; className: string }> = {
  estimated: { label: 'Estimated', className: 'badge badge-estimated' },
  verified: { label: 'Verified', className: 'badge badge-verified' },
  needs_review: { label: 'Needs Review', className: 'badge badge-needs-review' },
};

export function ScoreStateBadge({ state }: { state: ScoreState }): JSX.Element {
  const meta = SCORE_STATE_META[state];
  return (
    <span className={meta.className} title={`Score state: ${meta.label} (advisory, not an official grade)`}>
      {meta.label}
    </span>
  );
}

export function SecurityBadge({ status }: { status: SecurityStatus }): JSX.Element {
  const className =
    status === 'pass'
      ? 'badge badge-verified'
      : status === 'critical'
        ? 'badge badge-critical'
        : status === 'warning'
          ? 'badge badge-needs-review'
          : 'badge badge-unknown';
  const label =
    status === 'pass'
      ? 'Security: Pass'
      : status === 'critical'
        ? 'Security: Critical'
        : status === 'warning'
          ? 'Security: Warning'
          : 'Security: Unknown';
  return <span className={className}>{label}</span>;
}

export function DeploymentBadge({ reachable }: { reachable?: boolean | null }): JSX.Element {
  if (reachable == null) return <span className="badge badge-unknown">Deployment: Unknown</span>;
  return reachable ? (
    <span className="badge badge-verified">Deployment: Reachable</span>
  ) : (
    <span className="badge badge-critical">Deployment: Unreachable</span>
  );
}
