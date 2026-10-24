import { useCallback, useEffect, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { getProject, ApiError } from '../api/client';
import type { ProjectDetail } from '../types/api';

/**
 * Shared single-project loader — all HTTP goes through `api/client.ts`.
 * Exposes `setProject` so settings/override flows can apply server-returned
 * updates optimistically without a full refetch.
 */
export function useProject(projectId: string): {
  project: ProjectDetail | null;
  setProject: Dispatch<SetStateAction<ProjectDetail | null>>;
  loading: boolean;
  error: string | null;
  reload: () => void;
} {
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!projectId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getProject(projectId)
      .then((proj) => {
        if (!cancelled) setProject(proj);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Failed to load project.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, nonce]);

  return { project, setProject, loading, error, reload };
}
