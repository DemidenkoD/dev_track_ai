import { useState } from 'react';
import type { FormEvent } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { AdvisoryBanner } from '../components/badges';

export function LoginPage(): JSX.Element {
  const { login, loading, error } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState('reviewer@datatalks.club');
  const [password, setPassword] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setLocalError(null);
    try {
      await login(username.trim(), password);
      const from =
        (location.state as { from?: string } | null)?.from ?? '/dashboard';
      navigate(from, { replace: true });
    } catch {
      setLocalError('Login failed — check your credentials and try again.');
    }
  }

  return (
    <main className="page page-centered">
      <div className="card login-card">
        <h1>DevTrack AI</h1>
        <p className="muted">Your AI mentor from project idea to deployment.</p>
        <AdvisoryBanner />
        <form onSubmit={(e) => void handleSubmit(e)} className="stack">
          <label>
            Reviewer account
            <input
              type="email"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <p className="muted small">
            Pre-populated reviewer account: <code>reviewer@datatalks.club</code> (single predefined
            account — no public registration).
          </p>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {(localError ?? error) && (
            <p className="error" role="alert">
              {localError ?? error}
            </p>
          )}
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="muted small">
          Authenticated sessions use a JWT stored locally and sent as{' '}
          <code>Authorization: Bearer</code> on every <code>/api/v1</code> call.
        </p>
        <p className="muted small">
          <Link to="/dashboard">Continue to dashboard</Link> (requires sign-in)
        </p>
      </div>
    </main>
  );
}
