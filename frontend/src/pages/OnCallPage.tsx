import { OnCallPanel } from '../components/OnCallPanel';

export function OnCallPage(): JSX.Element {
  return (
    <main className="page">
      <header className="page-header">
        <div>
          <h1>Alert History</h1>
          <p className="muted">
            Past system alerts with plain-language explanations and suggested next steps.
            Read-only — a human always approves what happens next.
          </p>
        </div>
      </header>
      <OnCallPanel />
    </main>
  );
}
