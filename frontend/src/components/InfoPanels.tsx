import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type {
  AnalysisRun,
  DeploymentCheck,
  DiarySnapshot,
  EvidenceItem,
  EvidenceType,
  SecurityReport,
} from '../types/api';
import { EVIDENCE_TYPES } from '../types/api';
import { fetchEvidence, ApiError } from '../api/client';

/** Evidence / Diary / Security / Deployment tabs (read-only views). */
export function EvidencePanel({ items }: { items: EvidenceItem[] }): JSX.Element {
  if (items.length === 0)
    return (
      <div className="card stack" aria-live="polite">
        <p className="muted">
          No evidence collected yet for this project/run. The latest analysis completed but the
          backend returned <code>0 evidence_items</code> — there is nothing to display, not a
          loading error.
        </p>
        <p className="muted small">
          Evidence supports the advisory AI estimates on the Scorecard tab (<em>Estimated</em>{' '}
          = AI-only, <em>Verified</em> = human-confirmed, <em>Needs Review</em> = uncertain).
          Linked per-criterion evidence also appears inside each Scorecard card. Try clearing
          filters or picking a different analysis run above; if still empty, the root cause is
          upstream (worker persisted 0 rows), not this view.
        </p>
      </div>
    );
  return (
    <ul className="evidence-list">
      {items.map((ev) => (
        <li key={ev.id}>
          <EvidenceCard item={ev} />
        </li>
      ))}
    </ul>
  );
}

export function EvidenceCard({ item }: { item: EvidenceItem }): JSX.Element {
  return (
    <article className="card evidence-row">
      <span className="badge badge-unknown">{item.evidence_type}</span>
      <div className="evidence-body">
        <strong>{item.title}</strong>
        <p className="muted small">{item.path_or_url}</p>
        <dl className="evidence-meta">
          <div>
            <dt>Commit</dt>
            <dd>
              <code>{item.commit_sha ? item.commit_sha.slice(0, 8) : '—'}</code>
            </dd>
          </div>
          <div>
            <dt>Collected</dt>
            <dd>{item.created_at}</dd>
          </div>
          <div>
            <dt>Run</dt>
            <dd>
              <code>{item.analysis_run_id.slice(0, 8)}</code>
            </dd>
          </div>
        </dl>
        {item.snippet && (
          <pre className="snippet snippet-full" tabIndex={0} aria-label={`Full snippet for ${item.title}`}>
            {item.snippet}
          </pre>
        )}
        {item.metadata_json != null && Object.keys(item.metadata_json).length > 0 && (
          <details className="levels">
            <summary>Metadata</summary>
            <pre className="snippet snippet-full" tabIndex={0}>
              {JSON.stringify(item.metadata_json, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </article>
  );
}

/**
 * Evidence explorer with contract-backed filters.
 * Wires `GET /api/v1/projects/{id}/evidence?evidence_type=&analysis_run_id=`
 * via `fetchEvidence` — the only fetch path (api/client.ts).
 */
export function EvidenceExplorer({
  projectId,
  initialItems,
  runs,
}: {
  projectId: string;
  initialItems: EvidenceItem[];
  runs: AnalysisRun[];
}): JSX.Element {
  const [evidenceType, setEvidenceType] = useState<string>('');
  const [analysisRunId, setAnalysisRunId] = useState<string>('');
  const [items, setItems] = useState<EvidenceItem[]>(initialItems);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filtered, setFiltered] = useState(false);

  // Sync with freshly loaded project evidence (ProjectDetailPage fetches
  // asynchronously). Without this, `useState(initialItems)` freezes the first
  // empty array and the tab stays empty even after `load()` resolves or the
  // user picks a different analysis run — a stale-cache false-empty.
  useEffect(() => {
    if (!filtered) setItems(initialItems);
  }, [initialItems, filtered]);

  async function handleApply(event: FormEvent): Promise<void> {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await fetchEvidence(projectId, {
        evidence_type: evidenceType || undefined,
        analysis_run_id: analysisRunId.trim() || undefined,
      });
      setItems(result);
      setFiltered(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Evidence query failed.');
    } finally {
      setLoading(false);
    }
  }

  function handleReset(): void {
    setEvidenceType('');
    setAnalysisRunId('');
    setItems(initialItems);
    setFiltered(false);
    setError(null);
  }

  return (
    <section aria-label="Evidence explorer">
      <form className="card stack evidence-filters" onSubmit={(e) => void handleApply(e)}>
        <h3>Filter evidence</h3>
        <div className="filter-row">
          <label>
            Evidence type
            <select value={evidenceType} onChange={(e) => setEvidenceType(e.target.value)}>
              <option value="">All types</option>
              {EVIDENCE_TYPES.map((t: EvidenceType) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label>
            Analysis run ID
            <input
              value={analysisRunId}
              onChange={(e) => setAnalysisRunId(e.target.value)}
              placeholder="analysis_run_id (optional)"
              list="evidence-run-ids"
            />
            <datalist id="evidence-run-ids">
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.commit_sha?.slice(0, 8) ?? r.id.slice(0, 8)} · {r.status}
                </option>
              ))}
            </datalist>
          </label>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={handleReset}>
            Reset
          </button>
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? 'Querying…' : 'Apply filters'}
          </button>
        </div>
        {filtered && (
          <p className="muted small" aria-live="polite">
            Showing {items.length} item(s) for{' '}
            {evidenceType ? `type=${evidenceType}` : 'all types'}
            {analysisRunId.trim() ? ` · run=${analysisRunId.trim().slice(0, 8)}` : ''}.
          </p>
        )}
      </form>
      <EvidencePanel items={items} />
    </section>
  );
}

export interface DiaryPanelProps {
  diary: DiarySnapshot | null;
  summaryMarkdown?: string | null;
}

export function DiaryPanel({ diary, summaryMarkdown }: DiaryPanelProps): JSX.Element {
  const hasSummary = Boolean(summaryMarkdown && summaryMarkdown.trim().length > 0);
  if (!diary && !hasSummary) {
    return <p className="muted">No diary snapshot yet.</p>;
  }

  return (
    <div className="stack">
      {hasSummary && (
        <article className="card" aria-label="Executive summary">
          <header className="card-header">
            <h3>Executive summary</h3>
          </header>
          <pre className="snippet snippet-full" tabIndex={0}>
            {summaryMarkdown}
          </pre>
        </article>
      )}

      {diary ? (
        <div className="card">
          <p className="muted small">
            Discovered at <code>{diary.discovered_path}</code> · {diary.created_at}
          </p>
          <div className="diary-grid">
            <DiaryList title="Completed work" items={diary.completed_work ?? []} />
            <DiaryList title="Blockers" items={diary.blockers ?? []} />
            <DiaryList title="Decisions" items={diary.decisions ?? []} />
            <DiaryList title="Next steps" items={diary.next_steps ?? []} />
          </div>
          <h4>Git alignment</h4>
          <p>{diary.git_alignment_summary || 'No git alignment summary available.'}</p>
          {(diary.discrepancies ?? []).length > 0 && (
            <>
              <h4>Discrepancies (diary claims vs git reality)</h4>
              <ul>
                {(diary.discrepancies ?? []).map((d, i) => (
                  <li key={i}>
                    <strong>Claim:</strong> {d.claim} — <strong>Git reality:</strong> {d.git_reality}{' '}
                    <span
                      className={`badge ${d.severity === 'critical' ? 'badge-critical' : 'badge-needs-review'}`}
                    >
                      {d.severity}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      ) : (
        <div className="card">
          <p className="muted">No structured engineering diary snapshot discovered for this run.</p>
        </div>
      )}
    </div>
  );
}

function DiaryList({ title, items }: { title: string; items: string[] }): JSX.Element {
  return (
    <div>
      <h4>{title}</h4>
      {items.length === 0 ? (
        <p className="muted small">—</p>
      ) : (
        <ul>
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function SecurityPanel({ report }: { report: SecurityReport | null }): JSX.Element {
  if (!report) return <p className="muted">No security report yet.</p>;
  return (
    <div className="card">
      <header className="card-header">
        <div>
          <h3>Security report</h3>
          <p className="muted small">
            commit <code>{report.commit_sha.slice(0, 8)}</code> · scanners:{' '}
            {report.scanners_executed.join(', ') || 'none'}
          </p>
        </div>
        <span
          className={
            report.overall_status === 'pass'
              ? 'badge badge-verified'
              : report.overall_status === 'critical'
                ? 'badge badge-critical'
                : report.overall_status === 'warning'
                  ? 'badge badge-needs-review'
                  : 'badge badge-unknown'
          }
        >
          {report.overall_status}
        </span>
      </header>
      <p>{report.ai_executive_summary}</p>
      {report.findings.length === 0 ? (
        <p className="muted">No findings.</p>
      ) : (
        <ul className="evidence-list">
          {report.findings.map((f) => (
            <li key={f.id} className="evidence-row">
              <span className="badge badge-needs-review">
                {f.severity} · {f.scanner}
              </span>
              <div>
                <strong>
                  {f.rule_id}
                </strong>{' '}
                {f.file_path && (
                  <span className="muted small">
                    {f.file_path}
                    {f.line_number != null ? `:${f.line_number}` : ''}
                  </span>
                )}
                <p className="muted small">{f.raw_message}</p>
                {f.ai_explanation && <p>{f.ai_explanation}</p>}
                {f.ai_remediation && (
                  <p>
                    <strong>Remediation:</strong> {f.ai_remediation}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function DeploymentsPanel({
  checks,
  onCheckNow,
  checking,
}: {
  checks: DeploymentCheck[];
  onCheckNow: () => void;
  checking: boolean;
}): JSX.Element {
  return (
    <div>
      <button className="btn btn-secondary" onClick={onCheckNow} disabled={checking}>
        {checking ? 'Checking…' : 'Run live health check (SSRF-protected)'}
      </button>
      {checks.length === 0 && <p className="muted">No deployment checks recorded.</p>}
      <ul className="evidence-list">
        {checks.map((c) => (
          <li key={c.id} className="card evidence-row">
            <span className={c.is_reachable ? 'badge badge-verified' : 'badge badge-critical'}>
              {c.is_reachable ? 'reachable' : 'unreachable'}
            </span>
            <div>
              <strong>{c.target_url}</strong>
              <p className="muted small">
                source {c.discovery_source} · HTTP {c.http_status_code ?? '—'} · HTTPS{' '}
                {c.https_valid ? 'valid' : 'invalid'} ·{' '}
                {c.response_time_ms != null ? `${c.response_time_ms.toFixed(0)} ms` : 'latency n/a'} ·{' '}
                {c.checked_at}
              </p>
              {c.error_detail && <p className="error small">{c.error_detail}</p>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
