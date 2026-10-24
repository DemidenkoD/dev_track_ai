import { useState } from 'react';
import type { FormEvent } from 'react';
import { triggerAnalysis, ApiError } from '../api/client';

/**
 * Guardrail 5 — Manual analysis trigger modal with one-time email disclosure.
 * Sends `notify_email_once` + `acknowledge_ephemeral_email: true` only.
 * Email is never stored by the frontend; it is passed once per run.
 */
export function TriggerAnalysisModal({
  projectId,
  projectName,
  onClose,
  onTriggered,
}: {
  projectId: string;
  projectName: string;
  onClose: () => void;
  onTriggered: (runId: string) => void;
}): JSX.Element {
  const [wantEmail, setWantEmail] = useState(false);
  const [email, setEmail] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);
    if (wantEmail && !acknowledged) {
      setError('Please acknowledge the one-time email disclosure before continuing.');
      return;
    }
    setSubmitting(true);
    try {
      const run = await triggerAnalysis(projectId, {
        notify_email_once: wantEmail ? email.trim() || null : null,
        acknowledge_ephemeral_email: wantEmail,
      });
      onTriggered(run.id);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to trigger analysis.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Trigger analysis">
      <form className="modal" onSubmit={(e) => void handleSubmit(e)}>
        <h2>Run analysis — {projectName}</h2>
        <p className="muted">
          Queues a fresh advisory analysis of the public repository. DevTrack AI is read-only and
          advisory; it never modifies your repository.
        </p>

        <label className="check-row">
          <input
            type="checkbox"
            checked={wantEmail}
            onChange={(e) => setWantEmail(e.target.checked)}
          />
          Notify me by email when this run completes (one-time only)
        </label>

        {wantEmail && (
          <fieldset className="ephemeral-email">
            <legend>One-time email notification</legend>
            <label>
              Email address (used once for this run)
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required={wantEmail}
                autoComplete="email"
              />
            </label>
            <p className="disclosure" role="note">
              Your email address is held in volatile memory for this single run only, never stored
              in the database or logs, and may be lost if the server restarts.
            </p>
            <label className="check-row">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
              />
              I understand my email is used once for this run and never stored
              (acknowledge_ephemeral_email).
            </label>
          </fieldset>
        )}

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Queueing…' : 'Queue analysis run'}
          </button>
        </div>
      </form>
    </div>
  );
}
