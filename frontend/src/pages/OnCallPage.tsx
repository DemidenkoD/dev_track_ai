import { OnCallPanel } from '../components/OnCallPanel';

export function OnCallPage(): JSX.Element {
  return (
    <main className="page">
      <header className="page-header">
        <div>
          <h1>On-Call Diagnostics</h1>
          <p className="muted">
            Bounded, read-only incident diagnosis over Prometheus metrics, Loki logs, and Tempo
            traces.
          </p>
        </div>
      </header>
      <OnCallPanel />
    </main>
  );
}
