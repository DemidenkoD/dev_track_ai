import { Link } from 'react-router-dom';
import type { ProjectSummary } from '../types/api';
import { DeploymentBadge, ScoreStateBadge, SecurityBadge } from './badges';

function shortSha(sha?: string | null): string {
  if (!sha) return '—';
  return sha.slice(0, 8);
}

/**
 * Guardrail 1 — Project Dashboard card.
 * Shows Development Progress (%) and Expected Course Score (X/24) as two
 * DISTINCT metrics, plus deadline, last analysis SHA, security + deployment
 * badges. Scores are always advisory and carry score-state context.
 */
export function ProjectCard({ project }: { project: ProjectSummary }): JSX.Element {
  const dev = project.development_progress;
  const score = project.expected_score;
  return (
    <article className="card project-card" aria-label={`Project ${project.name}`}>
      <header className="card-header">
        <div>
          <h3>
            <Link to={`/projects/${project.id}`}>{project.name}</Link>
          </h3>
          <p className="muted small">
            {project.github_owner}/{project.github_repo} · {project.course_name}
          </p>
        </div>
        <span className={`badge status-${project.status}`}>{project.status}</span>
      </header>

      <div className="metric-grid">
        <div className="metric" aria-label="Development progress">
          <span className="metric-label">Development Progress</span>
          <span className="metric-value">{dev.completion_pct.toFixed(1)}%</span>
          <span className="muted small">
            {dev.completed_tasks}/{dev.total_tasks} tasks · {dev.partial_tasks} partial ·{' '}
            {dev.outstanding_tasks} outstanding
          </span>
          <progress value={dev.completion_pct} max={100} aria-label="Development completion" />
        </div>
        <div className="metric" aria-label="Expected course score">
          <span className="metric-label">Expected Course Score (advisory)</span>
          <span className="metric-value">
            {score.effective_points}/{score.max_points}
          </span>
          <span className="muted small">
            ✓ {score.verified_points} verified · ~ {score.estimated_points} estimated
            {score.passing_threshold != null &&
              ` · pass ≥ ${score.passing_threshold} (${score.meets_passing_threshold ? 'met' : 'not met'})`}
          </span>
        </div>
      </div>

      <dl className="card-meta">
        <div>
          <dt>Target date</dt>
          <dd>{project.target_date ?? '—'}</dd>
        </div>
        <div>
          <dt>Last analysis SHA</dt>
          <dd>
            <code>{shortSha(project.last_commit_sha)}</code>
          </dd>
        </div>
        <div>
          <dt>Last analysis</dt>
          <dd>{project.last_analysis_at ?? 'never'}</dd>
        </div>
      </dl>

      <footer className="card-footer">
        <SecurityBadge status={project.security_status} />
        <DeploymentBadge reachable={project.deployment_reachable} />
        {project.milestones_approved ? (
          <span className="badge badge-verified">Milestones approved</span>
        ) : (
          <span className="badge badge-needs-review">Milestones pending approval</span>
        )}
      </footer>

      <p className="muted small advisory-inline">
        AI estimates are advisory and never represent an official course grade.{' '}
        <ScoreStateBadge state={score.verified_points > 0 ? 'verified' : 'estimated'} />
      </p>
    </article>
  );
}
