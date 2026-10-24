import { defineConfig, devices } from '@playwright/test';

/**
 * Track 5 Playwright configuration for DevTrack AI.
 * baseURL targets the Vite dev server (frontend track); /api/v1 is proxied
 * to the backend per frontend/vite.config.ts. No live backend is required
 * for the invariant specs — they assert on mocked/stubbed UI states.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // Track 5: start the Vite dev server for UI assertions when it is not
  // already running. `reuseExistingServer: !CI` keeps local runs fast while
  // CI always boots a fresh server. API-dependent suites still skip gracefully
  // when the backend is absent — the webServer only guarantees the frontend.
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  },
});
