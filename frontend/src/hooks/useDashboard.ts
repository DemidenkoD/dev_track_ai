import { useCallback, useEffect, useState } from 'react';
import { fetchDashboard, fetchHealth, listRubrics, ApiError } from '../api/client';
import type { DashboardOverview, HealthResponse, RubricSummary } from '../types/api';

/**
 * Shared dashboard data hook — all HTTP goes through `api/client.ts`.
 * Returns dashboard overview + rubric list + backend health in one place
 * so DashboardPage and future pages share a single loading/error model.
 */
export function useDashboard(): {
  dashboard: DashboardOverview | null;
  rubrics: RubricSummary[];
  health: HealthResponse | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
} {
  const [dashboard, setDashboard] = useState<DashboardOverview | null>(null);
  const [rubrics, setRubrics] = useState<RubricSummary[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      fetchDashboard(),
      listRubrics().catch(() => [] as RubricSummary[]),
      fetchHealth().catch(() => null),
    ])
      .then(([dash, rubricList, healthResp]) => {
        if (cancelled) return;
        setDashboard(dash);
        setRubrics(rubricList);
        setHealth(healthResp);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Failed to load dashboard.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [nonce]);

  return { dashboard, rubrics, health, loading, error, reload };
}
