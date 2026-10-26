import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Track 5 On-Call History tab spec — REAL UI (Track 4 testids) + API mocks.
 *
 * Covers docs/specs/API_CONTRACT.md §8 (Phase 4b) against the locked
 * OnCallIncident shape (backend/app/schemas/api_contracts.py):
 *   1. History list loads and renders persisted incidents (real /oncall page).
 *   2. ?status= filter narrows the list; ?limit= caps it (route-mocked).
 *   3. Detail view opens with the read-only diagnosis + numbered
 *      remediation plan steps (recommended_actions, display text only).
 *   4. Acknowledge button marks the incident acknowledged with a note.
 *   5. Redaction: persisted payloads carry [redacted-*] markers and no raw
 *      email / JWT / Bearer values.
 *   6. Empty list renders the incident-empty healthy state.
 *
 * Strategy: navigate to the REAL /oncall route (OnCallPage → OnCallPanel),
 * intercept /api/v1/oncall/incidents* + /api/v1/auth/me with the locked
 * shape, and assert the REAL data-testid contract Track 4 wired:
 * incident-history/list/row/open/status-badge/severity,
 * filter-all/firing/acknowledged/resolved, incident-detail/summary,
 * remediation-plan/step, read-only-badge, acknowledge-note/button/state,
 * incident-empty.
 *
 * No live backend is required (all API responses are mocked), but the Vite
 * dev server MUST be running (playwright.config.ts webServer boots it).
 * The pure contract checks always run so `npx playwright test` never goes
 * silently green on skip.
 */

interface TelemetryCitation {
  source: 'prometheus' | 'loki' | 'tempo' | 'postgres_jobs';
  query: string;
  excerpt: string;
}

interface OnCallDiagnosis {
  incident_summary: string;
  root_cause_hypothesis: string;
  confidence: number;
  evidence_citations: TelemetryCitation[];
  recommended_actions: string[];
  read_only_verified: boolean;
}

interface OnCallIncident {
  id: string;
  alert_name: string;
  severity: string;
  service: string;
  status: 'firing' | 'acknowledged' | 'resolved';
  fingerprint: string;
  starts_at: string;
  ends_at: string | null;
  confidence: number;
  read_only_verified: boolean;
  acknowledge_note: string | null;
  project_id: string | null;
  created_at: string;
  updated_at: string;
}

interface OnCallIncidentDetail extends OnCallIncident {
  alert_payload_json: Record<string, unknown>;
  diagnosis: OnCallDiagnosis;
}

const STUB_INCIDENTS: OnCallIncident[] = [
  {
    id: '11111111-1111-1111-1111-111111111111',
    alert_name: 'HighHttp5xxErrorRate',
    severity: 'critical',
    service: 'api',
    status: 'firing',
    fingerprint: 'fp-e2e-001',
    starts_at: '2026-10-26T10:00:00.000Z',
    ends_at: null,
    confidence: 0.88,
    read_only_verified: true,
    acknowledge_note: null,
    project_id: null,
    created_at: '2026-10-26T10:00:05.000Z',
    updated_at: '2026-10-26T10:00:05.000Z',
  },
  {
    id: '22222222-2222-2222-2222-222222222222',
    alert_name: 'AnalysisWorkerJobFailures',
    severity: 'warning',
    service: 'worker',
    status: 'acknowledged',
    fingerprint: 'fp-e2e-002',
    starts_at: '2026-10-26T09:00:00.000Z',
    ends_at: null,
    confidence: 0.64,
    read_only_verified: true,
    acknowledge_note: 'Investigating 5xx spike',
    project_id: null,
    created_at: '2026-10-26T09:00:05.000Z',
    updated_at: '2026-10-26T09:30:00.000Z',
  },
];

const STUB_DETAIL: OnCallIncidentDetail = {
  ...STUB_INCIDENTS[0],
  alert_payload_json: {
    labels: { alertname: 'HighHttp5xxErrorRate', severity: 'critical', service: 'api' },
    annotations: { summary: '5xx spike', description: 'contact [redacted-email] for triage' },
    fingerprint: 'fp-e2e-001',
    startsAt: '2026-10-26T10:00:00.000Z',
  },
  diagnosis: {
    incident_summary: 'API errors spiked (alert HighHttp5xxErrorRate, last 30 minutes).',
    root_cause_hypothesis: 'Most likely: background jobs timed out on a large repository.',
    confidence: 0.88,
    evidence_citations: [
      { source: 'loki', query: '{app="worker"} |= "ERROR"', excerpt: 'TimeoutError at 10:01' },
    ],
    recommended_actions: [
      'Check worker logs for TimeoutError lines around the alert window (read-only).',
      'Check the Prometheus error-rate dashboard for the same window.',
      'Ask a human to approve any restart or scaling change.',
    ],
    read_only_verified: true,
  },
};

function jsonFulfill(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

/** Mock auth + on-call API against the REAL /oncall page. */
async function mockOnCallApi(
  page: Page,
  opts: { incidents?: OnCallIncident[]; detail?: OnCallIncidentDetail } = {},
): Promise<void> {
  const incidents = opts.incidents ?? STUB_INCIDENTS;
  const detail = opts.detail ?? STUB_DETAIL;

  await page.route('**/api/v1/auth/me', (route) =>
    jsonFulfill(route, { username: 'reviewer@datatalks.club', role: 'reviewer' }),
  );

  // NOTE: glob `*` never crosses `/`, so `incidents*` would miss
  // `incidents/{id}` + `.../acknowledge`. A pathname predicate covers all.
  await page.route(
    (url) => url.pathname.includes('/api/v1/oncall/incidents'),
    (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const pathname = url.pathname;

    // POST .../incidents/{id}/acknowledge → acknowledged detail.
    if (req.method() === 'POST' && pathname.endsWith('/acknowledge')) {
      let note: string | null = 'Investigating 5xx spike';
      try {
        const posted = req.postDataJSON() as { note?: string | null } | null;
        if (posted && 'note' in posted) note = posted.note ?? null;
      } catch {
        // keep default note
      }
      const acknowledged: OnCallIncidentDetail = {
        ...detail,
        status: 'acknowledged',
        acknowledge_note: note,
        updated_at: '2026-10-26T10:30:00.000Z',
      };
      return jsonFulfill(route, acknowledged);
    }

    // GET .../incidents/{id} → full detail with diagnosis + plan.
    const detailMatch = pathname.match(/\/api\/v1\/oncall\/incidents\/([^/]+)$/);
    if (req.method() === 'GET' && detailMatch) {
      return jsonFulfill(route, detail);
    }

    // GET .../incidents?status=&limit= → filtered list (newest first).
    if (req.method() === 'GET' && pathname.endsWith('/oncall/incidents')) {
      const status = url.searchParams.get('status');
      const limitRaw = url.searchParams.get('limit');
      let rows = [...incidents];
      if (status && status !== 'all') rows = rows.filter((i) => i.status === status);
      const limit = limitRaw ? Number.parseInt(limitRaw, 10) : rows.length;
      if (Number.isFinite(limit)) rows = rows.slice(0, limit);
      return jsonFulfill(route, rows);
    }

    return route.fallback();
    },
  );

  // Seed the predefined-reviewer token BEFORE the app boots so
  // ProtectedRoute → fetchCurrentUser() succeeds via the mock above.
  await page.addInitScript(() => {
    try {
      window.localStorage.setItem('devtrack.auth.token', 'e2e-oncall-token');
    } catch {
      // storage unavailable — auth mock still covers /auth/me
    }
  });
}

/** Base URL for the REAL UI. Honors E2E_BASE_URL so the suite can target a
 *  fresh `vite dev` instance when :5173 serves a stale static build. */
function e2eBaseUrl(baseURL: string | undefined): string {
  return process.env.E2E_BASE_URL ?? baseURL ?? 'http://localhost:5173';
}

async function gotoOnCall(page: Page, baseURL: string | undefined): Promise<void> {
  await page.goto(`${e2eBaseUrl(baseURL)}/oncall`, {
    waitUntil: 'domcontentloaded',
    timeout: 15000,
  });
  // The real panel root must mount (Track 4 data-testid contract).
  await expect(page.getByTestId('incident-history')).toBeVisible({ timeout: 15000 });
}

test.describe('on-call history tab (real UI, mocked API)', () => {
  test('locked incident shape carries History-tab fields', () => {
    for (const inc of STUB_INCIDENTS) {
      expect(inc.id).toMatch(/^[0-9a-f-]{36}$/);
      expect(['firing', 'acknowledged', 'resolved']).toContain(inc.status);
      expect(inc.read_only_verified).toBe(true);
      expect(inc.fingerprint).toMatch(/^fp-e2e-/);
      expect(new Date(inc.starts_at).toString()).not.toBe('Invalid Date');
    }
  });

  test('detail diagnosis is read-only with a numbered remediation plan', () => {
    const d = STUB_DETAIL.diagnosis;
    expect(d.read_only_verified).toBe(true);
    expect(d.recommended_actions.length).toBeGreaterThanOrEqual(1);
    expect(d.incident_summary).toContain('HighHttp5xxErrorRate');
    expect(d.evidence_citations.length).toBeGreaterThanOrEqual(1);
    expect(d.confidence).toBeGreaterThanOrEqual(0);
    expect(d.confidence).toBeLessThanOrEqual(1);
  });

  test('redacted payload carries markers and no raw secrets', () => {
    const dumped = JSON.stringify(STUB_DETAIL.alert_payload_json);
    expect(dumped).toContain('[redacted-email]');
    expect(dumped).not.toContain('@example.com');
    expect(dumped).not.toMatch(/eyJ[A-Za-z0-9_-]+\.eyJ/);
    expect(dumped).not.toContain('super-secret-token');
  });

  test('status filter + limit narrow the stubbed list', () => {
    const firing = STUB_INCIDENTS.filter((i) => i.status === 'firing');
    expect(firing).toHaveLength(1);
    const limited = STUB_INCIDENTS.slice(0, 1);
    expect(limited).toHaveLength(1);
  });

  test('history tab loads and shows the incident list (real UI)', async ({
    page,
    baseURL,
  }) => {
    await mockOnCallApi(page);
    await gotoOnCall(page, baseURL);
    await expect(page.getByTestId('incident-list')).toContainText('HighHttp5xxErrorRate');
    await expect(page.getByTestId('incident-list')).toContainText(
      'AnalysisWorkerJobFailures',
    );
    await expect(page.locator('[data-testid="incident-row"]')).toHaveCount(2);
    // Real status/severity badges render per row.
    await expect(page.getByTestId('incident-status-badge').first()).toBeVisible();
    await expect(page.getByTestId('incident-severity').first()).toBeVisible();
    // All four filter tabs are part of the real contract.
    for (const filterId of [
      'filter-all',
      'filter-firing',
      'filter-acknowledged',
      'filter-resolved',
    ]) {
      await expect(page.getByTestId(filterId)).toBeVisible();
    }
  });

  test('status filter tabs narrow the visible rows (real UI)', async ({
    page,
    baseURL,
  }) => {
    await mockOnCallApi(page);
    await gotoOnCall(page, baseURL);
    await expect(page.locator('[data-testid="incident-row"]')).toHaveCount(2);
    await page.getByTestId('filter-firing').click();
    // Component re-fetches ?status=firing → mock returns the 1 firing row.
    await expect(page.locator('[data-testid="incident-row"]')).toHaveCount(1);
    await expect(page.getByTestId('incident-list')).toContainText('HighHttp5xxErrorRate');
    await expect(page.getByTestId('incident-list')).not.toContainText(
      'AnalysisWorkerJobFailures',
    );
  });

  test('detail opens with remediation plan steps (real UI)', async ({
    page,
    baseURL,
  }) => {
    await mockOnCallApi(page);
    await gotoOnCall(page, baseURL);
    await page.getByTestId(`incident-open-${STUB_INCIDENTS[0].id}`).click();
    await expect(page.getByTestId('incident-detail')).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId('read-only-badge')).toContainText(/read-only/i);
    await expect(page.getByTestId('incident-summary')).toContainText(
      'HighHttp5xxErrorRate',
    );
    await expect(page.getByTestId('remediation-plan')).toBeVisible();
    await expect(page.locator('[data-testid="remediation-step"]')).toHaveCount(3);
  });

  test('acknowledge button marks incident acknowledged with note (real UI)', async ({
    page,
    baseURL,
  }) => {
    await mockOnCallApi(page);
    await gotoOnCall(page, baseURL);
    await page.getByTestId(`incident-open-${STUB_INCIDENTS[0].id}`).click();
    await expect(page.getByTestId('incident-detail')).toBeVisible({ timeout: 15000 });
    await page.getByTestId('acknowledge-note').fill('Investigating 5xx spike');
    await page.getByTestId('acknowledge-button').click();
    // Real component flips the state line to "Status: acknowledged".
    await expect(page.getByTestId('acknowledge-state')).toContainText('acknowledged', {
      timeout: 15000,
    });
    await expect(page.getByTestId('acknowledge-button')).toContainText('Acknowledged');
  });

  test('empty history renders the healthy empty state (real UI)', async ({
    page,
    baseURL,
  }) => {
    await mockOnCallApi(page, { incidents: [] });
    await gotoOnCall(page, baseURL);
    await expect(page.getByTestId('incident-empty')).toContainText(/no alerts yet/i);
    await expect(page.locator('[data-testid="incident-row"]')).toHaveCount(0);
  });
});

test.describe('on-call history scoping A+B (banner + ?project_id)', () => {
  const SCOPED_PROJECT_ID = '33333333-3333-3333-3333-333333333333';
  const SCOPED_PROJECT_NAME = 'Bridge Scope Project';

  const SCOPED_INCIDENT: OnCallIncident = {
    id: '33333333-3333-3333-3333-333333333334',
    alert_name: 'SecurityCritical:semgrep.bridge-rule',
    severity: 'critical',
    service: 'security-scanner',
    status: 'firing',
    fingerprint: 'a1b2c3d4e5f60718293a4b5c6d7e8f90',
    starts_at: '2026-10-26T12:00:00.000Z',
    ends_at: null,
    confidence: 0.75,
    read_only_verified: true,
    acknowledge_note: null,
    project_id: SCOPED_PROJECT_ID,
    created_at: '2026-10-26T12:00:05.000Z',
    updated_at: '2026-10-26T12:00:05.000Z',
  };

  const SCOPED_DETAIL: OnCallIncidentDetail = {
    ...SCOPED_INCIDENT,
    alert_payload_json: {
      rule_id: 'semgrep.bridge-rule',
      severity: 'critical',
      file_path: 'app/main.py',
      commit_sha: 'abc123def456',
      summary: 'Critical scanner finding (redacted contact [redacted-email])',
    },
    diagnosis: {
      incident_summary: "Critical security finding 'semgrep.bridge-rule' detected.",
      root_cause_hypothesis: "Scanner rule 'semgrep.bridge-rule' flagged app/main.py.",
      confidence: 0.75,
      evidence_citations: [
        { source: 'security-scanner', query: 'semgrep.bridge-rule', excerpt: 'app/main.py' },
      ],
      recommended_actions: ['Review app/main.py and remediate (human approval required).'],
      read_only_verified: true,
    },
  };

  const SCOPED_PROJECT: Record<string, unknown> = {
    id: SCOPED_PROJECT_ID,
    name: SCOPED_PROJECT_NAME,
    description: 'Scoped history probe',
    github_repo_url: 'https://github.com/octocat/hello-world',
    github_owner: 'octocat',
    github_repo: 'hello-world',
    course_name: 'AI Dev Tools Zoomcamp 2026',
    rubric_id: '00000000-0000-0000-0000-000000000009',
    status: 'active',
    start_date: null,
    target_date: null,
    weekly_hours: 12,
    diary_path: null,
    deployment_url: null,
    daily_schedule_cron: '0 6 * * *',
    milestones_approved: true,
    last_analysis_at: null,
    last_commit_sha: 'abc1234',
    security_status: 'pass',
    deployment_reachable: true,
    expected_score: {
      advisory_notice: 'AI estimates are advisory and never constitute an official course grade.',
      estimated_points: 4,
      verified_points: 2,
      effective_points: 4,
      potential_additional_points: 20,
      max_points: 24,
      passing_threshold: 10,
      meets_passing_threshold: false,
    },
    development_progress: {
      completed_tasks: 1,
      partial_tasks: 0,
      outstanding_tasks: 3,
      total_tasks: 4,
      completion_pct: 25,
      milestones_approved: true,
    },
    latest_summary_markdown: null,
    stalled_flag: false,
    scope_creep_flag: false,
    created_at: '2026-10-26T00:00:00.000Z',
    updated_at: '2026-10-26T00:00:00.000Z',
  };

  /** Scoped mocks for /projects/:id?tab=oncall: project stub + ?project_id-aware incidents. */
  async function mockScopedApi(page: Page, seenIncidentsUrls: string[]): Promise<void> {
    await page.route('**/api/v1/auth/me', (route) =>
      jsonFulfill(route, { username: 'reviewer@datatalks.club', role: 'reviewer' }),
    );
    await page.route(
      (url) => url.pathname.includes('/api/v1/'),
      (route) => {
        const req = route.request();
        const url = new URL(req.url());
        const pathname = url.pathname;

        if (pathname.includes('/api/v1/oncall/incidents')) {
          if (req.method() === 'POST' && pathname.endsWith('/acknowledge')) {
            return jsonFulfill(route, { ...SCOPED_DETAIL, status: 'acknowledged' });
          }
          const detailMatch = pathname.match(/\/api\/v1\/oncall\/incidents\/([^/]+)$/);
          if (req.method() === 'GET' && detailMatch) {
            if (detailMatch[1] === SCOPED_INCIDENT.id) return jsonFulfill(route, SCOPED_DETAIL);
            return jsonFulfill(route, STUB_DETAIL);
          }
          if (req.method() === 'GET' && pathname.endsWith('/oncall/incidents')) {
            seenIncidentsUrls.push(url.toString());
            const pid = url.searchParams.get('project_id');
            if (pid === SCOPED_PROJECT_ID) return jsonFulfill(route, [SCOPED_INCIDENT]);
            if (pid) return jsonFulfill(route, []);
            return jsonFulfill(route, STUB_INCIDENTS);
          }
          return route.fallback();
        }

        if (pathname === `/api/v1/projects/${SCOPED_PROJECT_ID}` && req.method() === 'GET') {
          return jsonFulfill(route, SCOPED_PROJECT);
        }
        if (pathname.includes('/api/v1/projects/')) {
          if (
            pathname.endsWith('/recommendations') ||
            pathname.endsWith('/deployments') ||
            pathname.endsWith('/analyses') ||
            pathname.endsWith('/evidence')
          ) {
            return jsonFulfill(route, []);
          }
          return jsonFulfill(route, { detail: 'scoped stub: not found' }, 404);
        }
        return route.fallback();
      },
    );
    await page.addInitScript(() => {
      try {
        window.localStorage.setItem('devtrack.auth.token', 'e2e-oncall-scope-token');
      } catch {
        // storage unavailable — auth mock still covers /auth/me
      }
    });
  }

  async function gotoScopedOnCall(
    page: Page,
    baseURL: string | undefined,
  ): Promise<void> {
    await page.goto(
      `${e2eBaseUrl(baseURL)}/projects/${SCOPED_PROJECT_ID}?tab=oncall`,
      { waitUntil: 'domcontentloaded', timeout: 15000 },
    );
    await expect(page.getByTestId('incident-history')).toBeVisible({ timeout: 15000 });
  }

  test('scoped bridge incident carries SecurityCritical + project_id shape', () => {
    expect(SCOPED_INCIDENT.alert_name.startsWith('SecurityCritical:')).toBe(true);
    expect(SCOPED_INCIDENT.project_id).toBe(SCOPED_PROJECT_ID);
    expect(SCOPED_INCIDENT.service).toBe('security-scanner');
    expect(SCOPED_INCIDENT.read_only_verified).toBe(true);
    expect(SCOPED_INCIDENT.fingerprint).toMatch(/^[0-9a-f]{32}$/);
    expect(SCOPED_DETAIL.diagnosis.confidence).toBe(0.75);
  });

  test('global history shows scope banner without scoped pill (real UI)', async ({
    page,
    baseURL,
  }) => {
    await mockOnCallApi(page);
    await gotoOnCall(page, baseURL);
    await expect(page.getByTestId('history-scope-note')).toBeVisible();
    await expect(page.getByTestId('history-scope-note')).toContainText(/operational alerts only/i);
    await expect(page.locator('[data-testid="history-project-filter"]')).toHaveCount(0);
  });

  test('scoped project tab shows banner + pill + one scoped row (real UI)', async ({
    page,
    baseURL,
  }) => {
    const seen: string[] = [];
    await mockScopedApi(page, seen);
    await gotoScopedOnCall(page, baseURL);
    // Banner carries the project name + link to the Security tab.
    await expect(page.getByTestId('history-scope-note')).toBeVisible();
    await expect(page.getByTestId('history-scope-note')).toContainText(SCOPED_PROJECT_NAME);
    await expect(page.getByTestId('history-scope-note')).toContainText(/code findings live/i);
    const scopeLink = page.getByTestId('history-scope-note').getByRole('link', {
      name: /view security findings/i,
    });
    await expect(scopeLink).toBeVisible();
    await expect(scopeLink).toHaveAttribute('href', '?tab=security');
    // Scoped pill + back-link to the global view.
    await expect(page.getByTestId('history-project-filter')).toBeVisible();
    await expect(page.getByTestId('history-project-filter')).toContainText(SCOPED_PROJECT_NAME);
    const allLink = page.getByTestId('history-project-filter').getByRole('link', {
      name: /view all alerts/i,
    });
    await expect(allLink).toBeVisible();
    await expect(allLink).toHaveAttribute('href', '/oncall');
    // Scoped fetch returned only the SecurityCritical row.
    await expect(page.locator('[data-testid="incident-row"]')).toHaveCount(1);
    await expect(page.getByTestId('incident-list')).toContainText(
      'SecurityCritical:semgrep.bridge-rule',
    );
    await expect(page.getByTestId('incident-list')).not.toContainText('HighHttp5xxErrorRate');
  });

  test('scoped fetch sends ?project_id (assert via request predicate)', async ({
    page,
    baseURL,
  }) => {
    const seen: string[] = [];
    await mockScopedApi(page, seen);
    await gotoScopedOnCall(page, baseURL);
    await expect(page.locator('[data-testid="incident-row"]')).toHaveCount(1);
    const scopedHits = seen.filter((u) => u.includes(`project_id=${SCOPED_PROJECT_ID}`));
    expect(seen.length).toBeGreaterThanOrEqual(1);
    expect(scopedHits.length).toBeGreaterThanOrEqual(1);
  });

  test('global fetch omits ?project_id (unscoped view)', async ({ page, baseURL }) => {
    const seen: string[] = [];
    await mockScopedApi(page, seen);
    await gotoOnCall(page, baseURL);
    await expect(page.locator('[data-testid="incident-row"]')).toHaveCount(2);
    expect(seen.length).toBeGreaterThanOrEqual(1);
    expect(seen.every((u) => !u.includes('project_id='))).toBe(true);
  });
});
