import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type {
  OnCallDiagnosisResponse,
  OnCallIncident,
  OnCallIncidentDetail,
  OnCallIncidentStatus,
} from '../types/api';
import {
  acknowledgeIncident,
  ApiError,
  diagnoseOnCall,
  getOnCallIncident,
  listOnCallIncidents,
} from '../api/client';
import { AdvisoryBanner } from './badges';

type StatusFilter = 'all' | OnCallIncidentStatus;

const STATUS_FILTERS: { id: StatusFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'firing', label: 'Active' },
  { id: 'acknowledged', label: 'Acknowledged' },
  { id: 'resolved', label: 'Resolved' },
];

/** Human-readable status label; raw `alert_name` stays visible but small. */
function statusLabel(status: OnCallIncidentStatus): string {
  if (status === 'firing') return 'Active';
  if (status === 'acknowledged') return 'Acknowledged';
  return 'Resolved';
}

function statusBadgeClass(status: OnCallIncidentStatus): string {
  if (status === 'firing') return 'badge badge-critical';
  if (status === 'acknowledged') return 'badge badge-estimated';
  return 'badge badge-verified';
}

function severityBadgeClass(severity: string): string {
  const s = severity.toLowerCase();
  if (s === 'critical') return 'badge badge-critical';
  if (s === 'high' || s === 'warning') return 'badge badge-needs-review';
  if (s === 'medium') return 'badge badge-estimated';
  return 'badge badge-unknown';
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

/**
 * Phase 4b — Alert History tab (human-understandable, no manual alert typing).
 *
 * Default view is the persisted Alertmanager alerts history list (newest
 * first) via `GET /api/v1/oncall/incidents`, exclusively through
 * `api/client.ts`. Selecting a row loads the full diagnosis +
 * remediation plan (`GET .../incidents/{id}`) with an acknowledge action
 * (`POST .../incidents/{id}/acknowledge`). The agent is read-only and
 * advisory: remediation steps are text to copy, never executed.
 */
export function OnCallPanel(): JSX.Element {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [incidents, setIncidents] = useState<OnCallIncident[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<OnCallIncidentDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [note, setNote] = useState('');
  const [ackLoading, setAckLoading] = useState(false);
  const [ackError, setAckError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Debug-only compat helper (collapsed, not prominent).
  const [debugAlert, setDebugAlert] = useState('HighAnalysisJobFailureRate');
  const [debugNotes, setDebugNotes] = useState('');
  const [debugResult, setDebugResult] = useState<OnCallDiagnosisResponse | null>(null);
  const [debugLoading, setDebugLoading] = useState(false);
  const [debugError, setDebugError] = useState<string | null>(null);

  const loadList = useCallback(
    async (silent = false) => {
      if (!silent) setListLoading(true);
      setListError(null);
      try {
        const rows = await listOnCallIncidents(statusFilter, 50);
        setIncidents(rows);
      } catch (err) {
        if (!silent) setListError(err instanceof ApiError ? err.message : 'Failed to load alert history.');
      } finally {
        if (!silent) setListLoading(false);
      }
    },
    [statusFilter],
  );

  useEffect(() => {
    void loadList();
  }, [loadList]);

  // Auto-refresh the list every 10s while any alert is still active,
  // mirroring the ProjectDetailPage 4s-while-pending polling pattern.
  const hasActive = incidents.some((i) => i.status === 'firing');
  useEffect(() => {
    if (!hasActive) return;
    const intervalId = window.setInterval(() => {
      void loadList(true);
    }, 10000);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [hasActive, loadList]);

  async function handleSelect(incident: OnCallIncident): Promise<void> {
    if (selectedId === incident.id && detail) return;
    setSelectedId(incident.id);
    setDetail(null);
    setDetailError(null);
    setAckError(null);
    setNote('');
    setCopied(false);
    setDetailLoading(true);
    try {
      const full = await getOnCallIncident(incident.id);
      setDetail(full);
    } catch (err) {
      setDetailError(err instanceof ApiError ? err.message : 'Failed to load alert details.');
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleAcknowledge(): Promise<void> {
    if (!detail) return;
    setAckLoading(true);
    setAckError(null);
    try {
      const updated = await acknowledgeIncident(detail.id, {
        note: note.trim() || null,
      });
      setDetail(updated);
      setIncidents((prev) =>
        prev.map((row) =>
          row.id === updated.id
            ? { ...row, status: updated.status, acknowledge_note: updated.acknowledge_note }
            : row,
        ),
      );
      setNote('');
    } catch (err) {
      setAckError(err instanceof ApiError ? err.message : 'Failed to acknowledge alert.');
    } finally {
      setAckLoading(false);
    }
  }

  async function handleCopyRunbook(): Promise<void> {
    if (!detail) return;
    const text = detail.diagnosis.recommended_actions
      .map((step, i) => `${i + 1}. ${step}`)
      .join('\n');
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  async function handleDebugDiagnose(event: FormEvent): Promise<void> {
    event.preventDefault();
    setDebugError(null);
    setDebugResult(null);
    if (!debugAlert.trim()) {
      setDebugError('Alert name is required.');
      return;
    }
    setDebugLoading(true);
    try {
      const result = await diagnoseOnCall({
        alert_name: debugAlert.trim(),
        time_window_minutes: 30,
        context_notes: debugNotes.trim() || null,
      });
      setDebugResult(result);
    } catch (err) {
      setDebugError(err instanceof ApiError ? err.message : 'On-call diagnosis failed.');
    } finally {
      setDebugLoading(false);
    }
  }

  return (
    <section aria-label="Alert history" className="stack" data-testid="incident-history">
      <AdvisoryBanner detail="Alert History is read-only and advisory. Diagnoses explain past alerts and propose human-approved next steps — nothing is executed automatically." />

      <div className="card stack">
        <header className="card-header">
          <h2>Alert History</h2>
          <button className="btn btn-secondary" onClick={() => void loadList()} disabled={listLoading}>
            {listLoading ? 'Loading…' : 'Refresh'}
          </button>
        </header>

        <div className="filter-row" role="group" aria-label="Filter alerts by status">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.id}
              data-testid={
                f.id === 'all'
                  ? 'filter-all'
                  : f.id === 'firing'
                    ? 'filter-firing'
                    : f.id === 'acknowledged'
                      ? 'filter-acknowledged'
                      : 'filter-resolved'
              }
              className={statusFilter === f.id ? 'tab tab-active' : 'tab'}
              onClick={() => setStatusFilter(f.id)}
              aria-pressed={statusFilter === f.id}
            >
              {f.label}
            </button>
          ))}
        </div>

        {listError && (
          <p className="error" role="alert">
            {listError}
          </p>
        )}

        {listLoading ? (
          <p aria-live="polite">Loading alerts…</p>
        ) : incidents.length === 0 ? (
          <p className="muted" aria-live="polite" data-testid="incident-empty">
            No alerts yet — system healthy
          </p>
        ) : (
          <ul className="run-list" aria-label="Alerts, newest first" data-testid="incident-list">
            {incidents.map((incident) => (
              <li
                key={incident.id}
                data-testid="incident-row"
                data-incident={incident.id}
                data-status={incident.status}
              >
                <button
                  data-testid={`incident-open-${incident.id}`}
                  className={selectedId === incident.id ? 'tab tab-active' : 'tab'}
                  onClick={() => void handleSelect(incident)}
                  aria-expanded={selectedId === incident.id}
                  style={{ width: '100%', textAlign: 'left' }}
                >
                  <span className={statusBadgeClass(incident.status)} data-testid="incident-status-badge">{statusLabel(incident.status)}</span>{' '}
                  <span className={severityBadgeClass(incident.severity)} data-testid="incident-severity">{incident.severity}</span>{' '}
                  <strong>{incident.service}</strong>{' '}
                  <span className="muted small">{incident.alert_name}</span>
                  <br />
                  <span className="muted small">
                    Started {formatDate(incident.starts_at)} · Confidence{' '}
                    {(incident.confidence * 100).toFixed(0)}%
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {selectedId && (
        <article
          className="card stack"
          aria-label="Alert details"
          aria-live="polite"
          data-testid="incident-detail"
          data-incident={selectedId ?? ''}
        >
          {detailLoading && <p>Loading alert details…</p>}
          {detailError && (
            <p className="error" role="alert">
              {detailError}
            </p>
          )}
          {detail && (
            <>
              <header className="card-header">
                <h3>
                  {statusLabel(detail.status)} — {detail.service}{' '}
                  <span className="muted small">{detail.alert_name}</span>
                </h3>
                <span className={statusBadgeClass(detail.status)}>{statusLabel(detail.status)}</span>
              </header>
              <p className="muted small">
                Started {formatDate(detail.starts_at)}
                {detail.ends_at ? ` · Ended ${formatDate(detail.ends_at)}` : ' · Still active'}
              </p>

              {detail.diagnosis.read_only_verified ? (
                <p>
                  <span
                    className="badge badge-verified"
                    title="The agent performed read-only inspection only"
                    data-testid="read-only-badge"
                  >
                    Read-only — human must approve
                  </span>
                </p>
              ) : (
                <p>
                  <span className="badge badge-needs-review" data-testid="read-only-badge">Read-only unverified</span>
                </p>
              )}

              <div>
                <h4>What happened</h4>
                <p data-testid="incident-summary">{detail.diagnosis.incident_summary || 'No summary available yet.'}</p>
              </div>

              <div>
                <h4>Likely cause</h4>
                <p>{detail.diagnosis.root_cause_hypothesis || 'No hypothesis available yet.'}</p>
                <p className="muted small">
                  Confidence: {(detail.diagnosis.confidence * 100).toFixed(0)}%
                </p>
                <progress
                  value={detail.diagnosis.confidence}
                  max={1}
                  aria-label="Diagnosis confidence"
                />
              </div>

              <div>
                <h4>Supporting evidence ({detail.diagnosis.evidence_citations.length})</h4>
                {detail.diagnosis.evidence_citations.length === 0 ? (
                  <p className="muted small">No telemetry citations returned.</p>
                ) : (
                  <ul className="evidence-list">
                    {detail.diagnosis.evidence_citations.map((cite, i) => (
                      <li key={i} className="card evidence-row">
                        <span className="badge badge-unknown">{cite.source}</span>
                        <div className="evidence-body">
                          <code className="small">{cite.query}</code>
                          <pre className="snippet snippet-full" tabIndex={0}>
                            {cite.excerpt}
                          </pre>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div>
                <h4>Suggested next steps (human approval required)</h4>
                {detail.diagnosis.recommended_actions.length === 0 ? (
                  <p className="muted small">No actions recommended.</p>
                ) : (
                  <>
                    <ol data-testid="remediation-plan">
                      {detail.diagnosis.recommended_actions.map((action, i) => (
                        <li key={i} data-testid="remediation-step">{action}</li>
                      ))}
                    </ol>
                    <button className="btn btn-secondary" onClick={() => void handleCopyRunbook()}>
                      {copied ? 'Copied to clipboard' : 'Copy steps as text'}
                    </button>
                  </>
                )}
              </div>

              <div className="card stack">
                <h4>Acknowledge this alert</h4>
                {detail.acknowledge_note && (
                  <p className="muted small">Previous note: {detail.acknowledge_note}</p>
                )}
                <label>
                  Note (optional)
                  <textarea
                    data-testid="acknowledge-note"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    rows={2}
                    placeholder="Investigating 5xx spike…"
                  />
                </label>
                {ackError && (
                  <p className="error" role="alert">
                    {ackError}
                  </p>
                )}
                <div className="modal-actions">
                  <button
                    data-testid="acknowledge-button"
                    className="btn btn-primary"
                    onClick={() => void handleAcknowledge()}
                    disabled={ackLoading || detail.status === 'acknowledged'}
                  >
                    {detail.status === 'acknowledged'
                      ? 'Acknowledged'
                      : ackLoading
                        ? 'Acknowledging…'
                        : 'Acknowledge'}
                  </button>
                </div>
                <p data-testid="acknowledge-state" className="muted small" aria-live="polite">
                  Status: {detail.status}
                </p>
              </div>
            </>
          )}
        </article>
      )}

      <details className="card stack">
        <summary className="muted small">Test diagnose (debug only, not part of the History view)</summary>
        <form className="stack" onSubmit={(e) => void handleDebugDiagnose(e)}>
          <label>
            Alert name
            <input
              value={debugAlert}
              onChange={(e) => setDebugAlert(e.target.value)}
              placeholder="HighAnalysisJobFailureRate"
            />
          </label>
          <label>
            Context notes (optional)
            <textarea
              value={debugNotes}
              onChange={(e) => setDebugNotes(e.target.value)}
              rows={2}
              placeholder="Worker jobs timing out on large repositories…"
            />
          </label>
          {debugError && (
            <p className="error" role="alert">
              {debugError}
            </p>
          )}
          <div className="modal-actions">
            <button type="submit" className="btn btn-secondary" disabled={debugLoading}>
              {debugLoading ? 'Diagnosing…' : 'Run read-only diagnosis'}
            </button>
          </div>
        </form>
        {debugResult && (
          <div className="stack">
            <p>{debugResult.incident_summary}</p>
            <p className="muted small">{debugResult.root_cause_hypothesis}</p>
          </div>
        )}
      </details>
    </section>
  );
}
