import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ingestRubric, listRubrics, ApiError } from '../api/client';
import type { RubricSourceType, RubricSummary } from '../types/api';
import { AdvisoryBanner } from '../components/badges';

export function RubricsPage(): JSX.Element {
  const [rubrics, setRubrics] = useState<RubricSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showIngest, setShowIngest] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRubrics(await listRubrics());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load rubrics.');
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
        <p aria-live="polite">Loading rubrics…</p>
      </main>
    );
  }

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <h1>Course Rubrics</h1>
          <p className="muted">
            {rubrics.length} versioned rubric(s). Rubrics are immutable once versioned — updating
            a rubric creates a new version.
          </p>
        </div>
        <div className="page-actions">
          <button className="btn btn-secondary" onClick={() => void load()}>
            Refresh
          </button>
          <button className="btn btn-primary" onClick={() => setShowIngest((v) => !v)}>
            {showIngest ? 'Close' : 'Ingest rubric'}
          </button>
        </div>
      </header>

      <AdvisoryBanner detail="Rubric criteria define official course point values. AI score estimates against these criteria are advisory and never represent an official course grade." />

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {showIngest && (
        <IngestRubricForm
          onDone={() => {
            setShowIngest(false);
            void load();
          }}
          onCancel={() => setShowIngest(false)}
        />
      )}

      <div className="project-grid">
        {rubrics.map((rubric) => (
          <article key={rubric.id} className="card">
            <header className="card-header">
              <div>
                <h3>
                  <Link to={`/rubrics/${rubric.id}`}>{rubric.title}</Link>
                </h3>
                <p className="muted small">
                  {rubric.course_name} · <code>{rubric.slug}</code>
                </p>
              </div>
              {rubric.is_official ? (
                <span className="badge badge-verified">Official</span>
              ) : (
                <span className="badge badge-estimated">Custom</span>
              )}
            </header>
            <dl className="card-meta">
              <div>
                <dt>Version</dt>
                <dd>
                  <code>{rubric.version}</code>
                </dd>
              </div>
              <div>
                <dt>Max points</dt>
                <dd>{rubric.max_points}</dd>
              </div>
              <div>
                <dt>Pass threshold</dt>
                <dd>{rubric.passing_threshold ?? '—'}</dd>
              </div>
            </dl>
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
              · retrieved {rubric.retrieved_at}
            </p>
          </article>
        ))}
      </div>
      {rubrics.length === 0 && <p className="muted">No rubrics available.</p>}
    </main>
  );
}

function IngestRubricForm({
  onDone,
  onCancel,
}: {
  onDone: () => void;
  onCancel: () => void;
}): JSX.Element {
  const [title, setTitle] = useState('');
  const [courseName, setCourseName] = useState('');
  const [sourceType, setSourceType] = useState<RubricSourceType>('url');
  const [sourceUrl, setSourceUrl] = useState('');
  const [rawContent, setRawContent] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);
    if (!title.trim() || !courseName.trim()) {
      setError('Title and course name are required.');
      return;
    }
    if (sourceType === 'url' && !sourceUrl.trim()) {
      setError('Source URL is required for source_type "url".');
      return;
    }
    if ((sourceType === 'markdown' || sourceType === 'text') && !rawContent.trim()) {
      setError('Pasted content is required for markdown/text ingestion.');
      return;
    }
    setSaving(true);
    try {
      await ingestRubric({
        title: title.trim(),
        course_name: courseName.trim(),
        source_type: sourceType,
        source_url: sourceUrl.trim() || null,
        raw_content: rawContent.trim() || null,
      });
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Rubric ingestion failed.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card stack" onSubmit={(e) => void handleSubmit(e)} aria-label="Ingest rubric">
      <h2>Ingest a course rubric</h2>
      <p className="muted small">
        The Rubric Analyst extracts official criteria, point values, and scoring levels. Public
        URLs only.
      </p>
      <div className="filter-row">
        <label>
          Title
          <input value={title} onChange={(e) => setTitle(e.target.value)} required />
        </label>
        <label>
          Course name
          <input value={courseName} onChange={(e) => setCourseName(e.target.value)} required />
        </label>
      </div>
      <div className="filter-row">
        <label>
          Source type
          <select value={sourceType} onChange={(e) => setSourceType(e.target.value as RubricSourceType)}>
            <option value="url">url</option>
            <option value="markdown">markdown</option>
            <option value="text">text</option>
            <option value="pdf">pdf</option>
            <option value="builtin">builtin</option>
          </select>
        </label>
        <label>
          Source URL
          <input
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
            placeholder="https://…"
            inputMode="url"
          />
        </label>
      </div>
      <label>
        Raw content (markdown / text ingestion)
        <textarea
          value={rawContent}
          onChange={(e) => setRawContent(e.target.value)}
          rows={5}
          placeholder="Paste rubric markdown or text…"
        />
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
          {saving ? 'Ingesting…' : 'Ingest rubric'}
        </button>
      </div>
    </form>
  );
}
