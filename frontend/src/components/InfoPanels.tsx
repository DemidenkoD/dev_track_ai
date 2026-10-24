import type {
  DeploymentCheck,
  DiarySnapshot,
  EvidenceItem,
  SecurityReport,
} from '../types/api';

/** Evidence / Diary / Security / Deployment tabs (read-only views). */
export function EvidencePanel({ items }: { items: EvidenceItem[] }): JSX.Element {
  if (items.length === 0) return <p className="muted">No evidence collected yet.</p>;
  return (
    <ul className="evidence-list">
      {items.map((ev) => (
        <li key={ev.id} className="card evidence-row">
          <span className="badge badge-unknown">{ev.evidence_type}</span>
          <div>
            <strong>{ev.title}</strong>
            <p className="muted small">{ev.path_or_url}</p>
            {ev.snippet && <pre className="snippet">{ev.snippet.slice(0, 500)}</pre>}
          </div>
        </li>
      ))}
    </ul>
  );
}

export function DiaryPanel({ diary }: { diary: DiarySnapshot | null }): JSX.Element {
  if (!diary) return <p className="muted">No diary snapshot yet.</p>;
  return (
    <div className="card">
      <p className="muted small">
        Discovered at <code>{diary.discovered_path}</code> · {diary.created_at}
      </p>
      <div className="diary-grid">
        <DiaryList title="Completed work" items={diary.completed_work} />
        <DiaryList title="Blockers" items={diary.blockers} />
        <DiaryList title="Decisions" items={diary.decisions} />
        <DiaryList title="Next steps" items={diary.next_steps} />
      </div>
      <h4>Git alignment</h4>
      <p>{diary.git_alignment_summary}</p>
      {diary.discrepancies.length > 0 && (
        <>
          <h4>Discrepancies (diary claims vs git reality)</h4>
          <ul>
            {diary.discrepancies.map((d, i) => (
              <li key={i}>
                <strong>Claim:</strong> {d.claim} — <strong>Git reality:</strong> {d.git_reality}{' '}
                <span className="badge badge-needs-review">{d.severity}</span>
              </li>
            ))}
          </ul>
        </>
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
