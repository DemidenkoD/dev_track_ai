import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getRubric, ApiError } from '../api/client';
import type { RubricDetail } from '../types/api';
import { AdvisoryBanner } from '../components/badges';

export function RubricDetailPage(): JSX.Element {
  const { rubricId = '' } = useParams();
  const [rubric, setRubric] = useState<RubricDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!rubricId) return;
    setLoading(true);
    setError(null);
    try {
      setRubric(await getRubric(rubricId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load rubric.');
    } finally {
      setLoading(false);
    }
  }, [rubricId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <main className="page">
        <p aria-live="polite">Loading rubric…</p>
      </main>
    );
  }

  if (!rubric) {
    return (
      <main className="page">
        <p className="error" role="alert">
          {error ?? 'Rubric not found.'}
        </p>
        <p>
          <Link to="/rubrics">Back to rubrics</Link>
        </p>
      </main>
    );
  }

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <h1>{rubric.title}</h1>
          <p className="muted">
            {rubric.course_name} · version <code>{rubric.version}</code> · max {rubric.max_points}{' '}
            pts · pass ≥ {rubric.passing_threshold ?? '—'}
          </p>
          <p className="muted small">
            Source: {rubric.source_type}
            {rubric.source_url ? (
              <>
                {' · '}
                <a href={rubric.source_url} target="_blank" rel="noreferrer">
                  {rubric.source_url}
                </a>
              </>
            ) : (
              ''
            )}{' '}
            · retrieved {rubric.retrieved_at}{' '}
            {rubric.is_official ? (
              <span className="badge badge-verified">Official</span>
            ) : (
              <span className="badge badge-estimated">Custom</span>
            )}
          </p>
        </div>
        <div className="page-actions">
          <Link to="/rubrics" className="btn btn-secondary">
            All rubrics
          </Link>
        </div>
      </header>

      <AdvisoryBanner detail="Criteria below carry official point values. AI estimates scored against them are advisory and never represent an official course grade." />

      <section aria-label="Rubric criteria">
        <h2>
          Criteria ({rubric.criteria.length})
        </h2>
        <div className="scorecard-grid">
          {rubric.criteria
            .slice()
            .sort((a, b) => a.display_order - b.display_order)
            .map((criterion) => (
              <article key={criterion.id} className="card">
                <header className="card-header">
                  <div>
                    <h3>
                      {criterion.name} <span className="muted small">({criterion.code})</span>
                    </h3>
                    <p className="muted small">
                      Max <strong>{criterion.max_points}</strong> pts · order {criterion.display_order}
                    </p>
                  </div>
                </header>
                <p>{criterion.description}</p>
                {criterion.scoring_levels.length > 0 ? (
                  <details className="levels" open>
                    <summary>Official scoring levels ({criterion.scoring_levels.length})</summary>
                    <ul>
                      {criterion.scoring_levels.map((level, i) => (
                        <li key={i}>
                          <strong>{level.points} pts</strong> — {level.description}
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : (
                  <p className="muted small">No scoring levels recorded.</p>
                )}
                {criterion.required_evidence_types.length > 0 && (
                  <p className="muted small">
                    Expected evidence:{' '}
                    {criterion.required_evidence_types.map((t) => (
                      <span key={t} className="badge badge-unknown">
                        {t}
                      </span>
                    ))}
                  </p>
                )}
              </article>
            ))}
        </div>
      </section>
    </main>
  );
}
