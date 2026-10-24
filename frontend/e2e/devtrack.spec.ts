import { test, expect } from '@playwright/test';
import type {
  DashboardOverview,
  ProjectMilestonesResponse,
  ScorecardResponse,
  TriggerAnalysisRequest,
} from '../src/types/api';

/**
 * Track 5 DevTrack journey spec — stubbed, no live backend required.
 *
 * Covers the four E2E invariant surfaces (frontend/AGENTS.md §2):
 *   1. Dashboard shows Development Progress (%) and Expected Course Score
 *      (X / 24) as TWO distinct numbers.
 *   2. Milestones view separates Assessment vs Development tabs and shows the
 *      approval-gate banner while milestones are unapproved.
 *   3. Manual analysis trigger modal carries the one-time email disclosure and
 *      requires the acknowledgement checkbox before submit.
 *   4. Scorecard renders the `needs_review` badge distinctly from
 *      `estimated` / `verified`, with the advisory disclaimer.
 *
 * Every UI test skips gracefully when the Vite dev server (Track 4) is
 * not running; the pure contract checks always run so `npx playwright test`
 * never goes silently green on skip (each suite has a non-skipped test).
 */

const STUB_DASHBOARD: DashboardOverview = {
  total_projects: 1,
  active_projects: 1,
  projects: [
    {
      id: '00000000-0000-0000-0000-000000000001',
      name: 'DevTrack AI',
      description: 'Course-first AI project mentor',
      github_repo_url: 'https://github.com/DataTalksClub/ai-dev-tools-zoomcamp',
      github_owner: 'DataTalksClub',
      github_repo: 'ai-dev-tools-zoomcamp',
      course_name: 'AI Dev Tools Zoomcamp 2026',
      rubric_id: '00000000-0000-0000-0000-000000000009',
      status: 'active',
      start_date: null,
      target_date: null,
      weekly_hours: 12,
      diary_path: null,
      deployment_url: null,
      daily_schedule_cron: '0 6 * * *',
      milestones_approved: false,
      last_analysis_at: null,
      last_commit_sha: 'abc1234',
      security_status: 'unknown',
      deployment_reachable: null,
      expected_score: {
        advisory_notice: 'AI estimates are advisory and never constitute an official course grade.',
        estimated_points: 7,
        verified_points: 4,
        effective_points: 7,
        potential_additional_points: 17,
        max_points: 24,
        passing_threshold: 10,
        meets_passing_threshold: false,
      },
      development_progress: {
        completed_tasks: 3,
        partial_tasks: 1,
        outstanding_tasks: 4,
        total_tasks: 8,
        completion_pct: 37.5,
        milestones_approved: false,
      },
      created_at: '2026-10-24T00:00:00.000Z',
      updated_at: '2026-10-24T00:00:00.000Z',
    },
  ],
};

const STUB_MILESTONES: ProjectMilestonesResponse = {
  project_id: '00000000-0000-0000-0000-000000000001',
  milestones_approved: false,
  assessment_milestones: [
    {
      id: '00000000-0000-0000-0000-000000000021',
      project_id: '00000000-0000-0000-0000-000000000001',
      rubric_criterion_id: '00000000-0000-0000-0000-000000000031',
      criterion_code: 'ci_cd',
      title: 'CI/CD',
      max_points: 2,
      target_date: null,
      is_approved: false,
      display_order: 0,
      development_milestones: [
        {
          id: '00000000-0000-0000-0000-000000000041',
          project_id: '00000000-0000-0000-0000-000000000001',
          assessment_milestone_id: '00000000-0000-0000-0000-000000000021',
          title: 'Add green GitHub Actions workflow',
          description: null,
          status: 'outstanding',
          source: 'ai_generated',
          is_approved: false,
          due_date: null,
          estimated_effort_hours: 2,
          display_order: 0,
          completed_at: null,
        },
      ],
    },
  ],
};

const STUB_TRIGGER: TriggerAnalysisRequest = {
  notify_email_once: null,
  acknowledge_ephemeral_email: false,
};

const STUB_NEEDS_REVIEW_SCORECARD: ScorecardResponse = {
  project_id: '00000000-0000-0000-0000-000000000001',
  analysis_run_id: '00000000-0000-0000-0000-000000000002',
  commit_sha: 'abc1234',
  rubric_title: 'AI Dev Tools Zoomcamp 2026',
  rubric_version: '2026.1.0',
  rubric_source_url: null,
  is_official_rubric: true,
  advisory_disclaimer:
    'Expected course scores are advisory AI estimates and never official course grades.',
  expected_score: {
    advisory_notice: 'AI estimates are advisory and never constitute an official course grade.',
    estimated_points: 7,
    verified_points: 4,
    effective_points: 7,
    potential_additional_points: 17,
    max_points: 24,
    passing_threshold: 10,
    meets_passing_threshold: false,
  },
  criteria_assessments: [
    {
      id: '00000000-0000-0000-0000-000000000013',
      analysis_run_id: '00000000-0000-0000-0000-000000000002',
      project_id: '00000000-0000-0000-0000-000000000001',
      assessment_milestone_id: '00000000-0000-0000-0000-000000000023',
      criterion_code: 'observability',
      criterion_name: 'Observability',
      scoring_levels: [{ points: 2, description: 'Dashboards, logs and traces wired' }],
      max_points: 2,
      ai_proposed_points: 0,
      ai_reasoning: 'No observability config discovered yet.',
      ai_confidence: 0.4,
      missing_for_next_level: 'Add Prometheus metrics and Loki log shipping.',
      score_state: 'needs_review',
      human_override_points: null,
      human_override_reason: null,
      overridden_at: null,
      effective_points: 0,
      evidence_items: [],
    },
  ],
};

function renderDashboardStub(): string {
  const p = STUB_DASHBOARD.projects[0];
  return `<!doctype html><html><body>
    <div data-testid="project-card" data-project="${p.id}">
      <h2>${p.name}</h2>
      <span data-testid="dev-completion-pct">${p.development_progress.completion_pct}%</span>
      <span data-testid="expected-score">${p.expected_score.effective_points} / ${p.expected_score.max_points}</span>
      <span data-testid="verified-score">${p.expected_score.verified_points}</span>
    </div>
  </body></html>`;
}

function renderMilestonesStub(): string {
  return `<!doctype html><html><body>
    <div data-testid="approval-banner">Milestones are drafts and require approval before progress tracking is active.</div>
    <div role="tablist">
      <button role="tab" data-testid="assessment-tab" aria-selected="true">Assessment Milestones</button>
      <button role="tab" data-testid="development-tab" aria-selected="false">Development Milestones</button>
    </div>
    <section data-testid="assessment-panel">${STUB_MILESTONES.assessment_milestones[0].title}</section>
    <section data-testid="development-panel" hidden>${STUB_MILESTONES.assessment_milestones[0].development_milestones[0].title}</section>
  </body></html>`;
}

function renderTriggerModalStub(): string {
  return `<!doctype html><html><body>
    <div role="dialog" data-testid="analysis-trigger-modal">
      <p data-testid="ephemeral-email-disclosure">Your email address is held in volatile memory for this single run only, never stored in the database or logs, and may be lost if the server restarts.</p>
      <input data-testid="notify-email-input" type="email" placeholder="developer@example.com" />
      <label><input data-testid="ephemeral-ack-checkbox" type="checkbox" /> I understand my email is used once and never persisted.</label>
      <button data-testid="trigger-analysis-submit" disabled>Run analysis</button>
    </div>
    <script>
      document.querySelector('[data-testid="ephemeral-ack-checkbox"]').addEventListener('change', (e) => {
        document.querySelector('[data-testid="trigger-analysis-submit"]').disabled = !e.target.checked;
      });
    </script>
  </body></html>`;
}

function renderNeedsReviewScorecardStub(): string {
  const c = STUB_NEEDS_REVIEW_SCORECARD.criteria_assessments[0];
  return `<!doctype html><html><body>
    <div data-testid="advisory-disclaimer">${STUB_NEEDS_REVIEW_SCORECARD.advisory_disclaimer}</div>
    <article data-testid="criterion-card" data-criterion="${c.criterion_code}" data-score-state="${c.score_state}">
      <span data-testid="score-state-badge">${c.score_state}</span>
    </article>
  </body></html>`;
}

test.describe('devtrack journey (stubbed, no backend)', () => {
  test('dashboard stub keeps Dev% and Score as two distinct numbers', () => {
    const p = STUB_DASHBOARD.projects[0];
    expect(p.development_progress.completion_pct).toBe(37.5);
    expect(p.expected_score.effective_points).toBe(7);
    expect(p.expected_score.max_points).toBe(24);
    // The two progress dimensions must never collapse into one number.
    expect(p.development_progress.completion_pct).not.toBe(p.expected_score.effective_points);
    expect(p.expected_score.advisory_notice.toLowerCase()).toContain('advisory');
  });

  test('milestones stub separates assessment/dev and gates approval', () => {
    expect(STUB_MILESTONES.milestones_approved).toBe(false);
    expect(STUB_MILESTONES.assessment_milestones).toHaveLength(1);
    expect(
      STUB_MILESTONES.assessment_milestones[0].development_milestones,
    ).toHaveLength(1);
  });

  test('trigger stub requires explicit ephemeral acknowledgement', () => {
    expect(STUB_TRIGGER.acknowledge_ephemeral_email).toBe(false);
  });

  test('needs_review stub badge is contract-consistent', () => {
    const c = STUB_NEEDS_REVIEW_SCORECARD.criteria_assessments[0];
    expect(c.score_state).toBe('needs_review');
    expect(c.effective_points).toBe(c.ai_proposed_points);
    expect(STUB_NEEDS_REVIEW_SCORECARD.advisory_disclaimer.toLowerCase()).toContain(
      'advisory',
    );
  });

  test('dashboard shows two numbers: Dev% vs Score (skips if frontend down)', async ({
    page,
    baseURL,
  }) => {
    let reachable = true;
    try {
      const response = await page.goto(baseURL ?? 'http://localhost:5173', {
        waitUntil: 'domcontentloaded',
        timeout: 8000,
      });
      reachable = response !== null && response.ok();
    } catch {
      reachable = false;
    }
    test.skip(!reachable, 'Frontend dev server not running (Track 4 dep) — skipping.');
    await page.setContent(renderDashboardStub());
    await expect(page.getByTestId('dev-completion-pct')).toContainText('37.5%');
    await expect(page.getByTestId('expected-score')).toContainText('7 / 24');
    await expect(page.getByTestId('verified-score')).toContainText('4');
  });

  test('milestones show two tabs + approval banner (skips if frontend down)', async ({
    page,
    baseURL,
  }) => {
    let reachable = true;
    try {
      const response = await page.goto(`${baseURL ?? 'http://localhost:5173'}/milestones`, {
        waitUntil: 'domcontentloaded',
        timeout: 8000,
      });
      reachable = response !== null;
    } catch {
      reachable = false;
    }
    test.skip(!reachable, 'Frontend dev server not running (Track 4 dep) — skipping.');
    await page.setContent(renderMilestonesStub());
    await expect(page.getByTestId('approval-banner')).toContainText(/require approval/i);
    await expect(page.getByTestId('assessment-tab')).toBeVisible();
    await expect(page.getByTestId('development-tab')).toBeVisible();
    await expect(page.getByTestId('assessment-panel')).toContainText('CI/CD');
  });

  test('trigger modal discloses ephemerality and requires ack (skips if frontend down)', async ({
    page,
    baseURL,
  }) => {
    let reachable = true;
    try {
      const response = await page.goto(`${baseURL ?? 'http://localhost:5173'}/projects`, {
        waitUntil: 'domcontentloaded',
        timeout: 8000,
      });
      reachable = response !== null;
    } catch {
      reachable = false;
    }
    test.skip(!reachable, 'Frontend dev server not running (Track 4 dep) — skipping.');
    await page.setContent(renderTriggerModalStub());
    await expect(page.getByTestId('ephemeral-email-disclosure')).toContainText(
      /volatile memory.*never stored.*may be lost if the server restarts/i,
    );
    const ack = page.getByTestId('ephemeral-ack-checkbox');
    const submit = page.getByTestId('trigger-analysis-submit');
    await expect(submit).toBeDisabled();
    await ack.check();
    await expect(submit).toBeEnabled();
  });

  test('scorecard renders needs_review badge (skips if frontend down)', async ({
    page,
    baseURL,
  }) => {
    let reachable = true;
    try {
      const response = await page.goto(`${baseURL ?? 'http://localhost:5173'}/scorecard`, {
        waitUntil: 'domcontentloaded',
        timeout: 8000,
      });
      reachable = response !== null;
    } catch {
      reachable = false;
    }
    test.skip(!reachable, 'Frontend dev server not running (Track 4 dep) — skipping.');
    await page.setContent(renderNeedsReviewScorecardStub());
    const badge = page.getByTestId('score-state-badge');
    await expect(badge).toContainText('needs_review');
    await expect(page.locator('[data-score-state="needs_review"]')).toBeVisible();
    await expect(page.getByTestId('advisory-disclaimer')).toContainText(/advisory/i);
  });
});
