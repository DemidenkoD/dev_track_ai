import { useEffect, useState } from 'react';
import { Link, Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { getStoredToken } from './api/client';
import { ProtectedRoute } from './components/ProtectedRoute';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { ProjectDetailPage } from './pages/ProjectDetailPage';
import { RubricsPage } from './pages/RubricsPage';
import { RubricDetailPage } from './pages/RubricDetailPage';
import { OnCallPage } from './pages/OnCallPage';

function ThemeToggle(): JSX.Element {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try {
      return (window.localStorage.getItem('devtrack.theme') as 'light' | 'dark') ?? 'dark';
    } catch {
      return 'dark';
    }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem('devtrack.theme', theme);
    } catch {
      // ignore
    }
  }, [theme]);
  return (
    <button
      className="btn btn-ghost"
      onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
    >
      {theme === 'dark' ? '☀ Light' : '☾ Dark'}
    </button>
  );
}

function NavBar(): JSX.Element {
  const { isAuthenticated, user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <header className="navbar">
      <Link to="/dashboard" className="brand">
        DevTrack AI
      </Link>
      <nav className="nav-links" aria-label="Primary">
        {isAuthenticated && (
          <>
            <Link to="/dashboard">Dashboard</Link>
            <Link to="/rubrics">Rubrics</Link>
            <Link to="/oncall">On-Call</Link>
          </>
        )}
      </nav>
      <div className="nav-right">
        <ThemeToggle />
        {isAuthenticated ? (
          <>
            <span className="muted small reviewer-banner" title="Signed in as predefined reviewer">
              {user?.username ?? 'reviewer'} · {user?.role ?? 'reviewer'}
            </span>
            <button
              className="btn btn-secondary"
              onClick={() => {
                logout();
                navigate('/login');
              }}
            >
              Sign out
            </button>
          </>
        ) : (
          <Link to="/login" className="btn btn-primary">
            Sign in
          </Link>
        )}
      </div>
    </header>
  );
}

function RootRedirect(): JSX.Element {
  return <Navigate to={getStoredToken() ? '/dashboard' : '/login'} replace />;
}

export function App(): JSX.Element {
  return (
    <AuthProvider>
      <div className="app-shell">
        <NavBar />
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <DashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/projects/:projectId"
            element={
              <ProtectedRoute>
                <ProjectDetailPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/rubrics"
            element={
              <ProtectedRoute>
                <RubricsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/rubrics/:rubricId"
            element={
              <ProtectedRoute>
                <RubricDetailPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/oncall"
            element={
              <ProtectedRoute>
                <OnCallPage />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<RootRedirect />} />
        </Routes>
        <footer className="footer muted small">
          DevTrack AI is advisory and read-only. AI-estimated points are advisory and never
          represent an official course grade.
        </footer>
      </div>
    </AuthProvider>
  );
}
