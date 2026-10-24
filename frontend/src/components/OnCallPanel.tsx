import { useState } from 'react';
import type { FormEvent } from 'react';
import type { OnCallDiagnosisResponse } from '../types/api';
import { diagnoseOnCall, ApiError } from '../api/client';
import { AdvisoryBanner } from './badges';

/**
 * Phase 4 — Bounded read-only On-Call diagnostics.
 * Invokes `POST /api/v1/oncall/diagnose` (read-only Prometheus/Loki/Tempo
 * inspection) exclusively via `api/client.ts`. The agent proposes safe,
 * human-approved remediation steps only; it never mutates infrastructure.
 */
export function OnCallPanel({ defaultContextNotes }: { defaultContextNotes?: string }): JSX.Element {
  const [alertName, setAlertName] = useState('HighAnalysisJobFailureRate');
  const [timeWindow, setTimeWindow] = useState('30');
  const [contextNotes, setContextNotes] = useState(defaultContextNotes ?? '');
  const [diagnosis, setDiagnosis] = useState<OnCallDiagnosisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);
    setDiagnosis(null);
    if (!alertName.trim()) {
      setError('Alert name is required.');
      return;
    }
    const minutes = timeWindow.trim() === '' ? undefined : Number(timeWindow);
    if (minutes !== undefined && (!Number.isInteger(minutes) || minutes <= 0)) {
      setError('Time window must be a positive integer number of minutes (or blank).');
      return;
    }
    setLoading(true);
    try {
      const result = await diagnoseOnCall({
        alert_name: alertName.trim(),
        time_window_minutes: minutes,
        context_notes: contextNotes.trim() || null,
      });
      setDiagnosis(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'On-call diagnosis failed.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-label="On-call diagnostics" className="stack">
      <AdvisoryBanner detail="On-Call diagnosis is read-only and advisory. It inspects telemetry and proposes safe human-approved remediation steps — it never changes infrastructure." />
      <form className="card stack" onSubmit={(e) => void handleSubmit(e)}>
        <h2>On-call diagnosis (read-only)</h2>
        <label>
          Alert name
          <input
            value={alertName}
            onChange={(e) => setAlertName(e.target.value)}
            placeholder="HighAnalysisJobFailureRate"
            required
          />
        </label>
        <div className="filter-row">
          <label>
            Time window (minutes)
            <input
              type="number"
              min={1}
              value={timeWindow}
              onChange={(e) => setTimeWindow(e.target.value)}
              placeholder="30"
            />
          </label>
        </div>
        <label>
          Context notes (optional)
          <textarea
            value={contextNotes}
            onChange={(e) => setContextNotes(e.target.value)}
            rows={3}
            placeholder="Worker jobs timing out on large repositories…"
          />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? 'Diagnosing…' : 'Run read-only diagnosis'}
          </button>
        </div>
      </form>

      {diagnosis && (
        <article className="card stack" aria-label="Diagnosis result" aria-live="polite">
          <header className="card-header">
            <h3>Diagnosis</h3>
            {diagnosis.read_only_verified ? (
              <span className="badge badge-verified" title="The agent performed read-only inspection only">
                Read-only verified
              </span>
            ) : (
              <span className="badge badge-needs-review">Read-only unverified</span>
            )}
          </header>
          <div>
            <h4>Incident summary</h4>
            <p>{diagnosis.incident_summary}</p>
          </div>
          <div>
            <h4>Root-cause hypothesis</h4>
            <p>{diagnosis.root_cause_hypothesis}</p>
            <p className="muted small">Confidence: {(diagnosis.confidence * 100).toFixed(0)}%</p>
            <progress value={diagnosis.confidence} max={1} aria-label="Diagnosis confidence" />
          </div>
          <div>
            <h4>Evidence citations ({diagnosis.evidence_citations.length})</h4>
            {diagnosis.evidence_citations.length === 0 ? (
              <p className="muted small">No telemetry citations returned.</p>
            ) : (
              <ul className="evidence-list">
                {diagnosis.evidence_citations.map((cite, i) => (
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
            <h4>Recommended actions (human approval required)</h4>
            {diagnosis.recommended_actions.length === 0 ? (
              <p className="muted small">No actions recommended.</p>
            ) : (
              <ol>
                {diagnosis.recommended_actions.map((action, i) => (
                  <li key={i}>{action}</li>
                ))}
              </ol>
            )}
          </div>
        </article>
      )}
    </section>
  );
}
