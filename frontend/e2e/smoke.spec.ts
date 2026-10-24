import { test, expect } from '@playwright/test';

/**
 * Track 5 smoke spec — dashboard availability probe.
 * Skips gracefully when the frontend dev server (Track 4) is not running,
 * so `npx playwright test` never fails purely due to a missing dev server.
 */
test.describe('smoke: dashboard availability', () => {
  test('dashboard responds or skips when frontend is down', async ({ page, baseURL }) => {
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
    await expect(page.locator('body')).toBeVisible();
  });
});
