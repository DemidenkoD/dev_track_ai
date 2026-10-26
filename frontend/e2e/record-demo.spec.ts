import { test, expect } from '@playwright/test';
import * as path from 'path';
import * as fs from 'fs';

/**
 * Automated Demo Video Recording Spec
 *
 * Drives the in-app DevTrack AI Guided Demo with ElevenLabs voiceover integration
 * and records a 720p HD video walkthrough to demo/devtrack_ai_demo.webm.
 */
test.use({
  baseURL: process.env.BASE_URL || process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173',
  video: {
    mode: 'on',
    size: { width: 1280, height: 720 },
  },
  viewport: { width: 1280, height: 720 },
});

test('record full DevTrack AI application demo walkthrough', async ({ page }) => {
  test.skip(!process.env.RECORD_DEMO, 'Set RECORD_DEMO=1 to record walkthrough video');

  // Allow ample time for the full 7-scene guided video recording
  test.setTimeout(90000);

  // Navigate to application in demo mode
  await page.goto('/?demo=true', { waitUntil: 'networkidle' });

  // Locate and click the "🎬 Guided Demo" button in the Navbar
  const startDemoBtn = page.locator('[data-testid="start-demo-btn"]');
  await expect(startDemoBtn).toBeVisible();
  await startDemoBtn.click();

  // Verify Demo Tour HUD teleprompter appears
  const hud = page.locator('[data-testid="demo-tour-hud"]');
  await expect(hud).toBeVisible();

  // Helper to click next scene
  const nextBtn = page.locator('[data-testid="demo-next-btn"]');

  // --- SCENE 1: Introduction & The Core Problem ---
  console.log('Recording Scene 1: Introduction...');
  await page.waitForTimeout(3500);

  // --- SCENE 2: Reviewer Login & Project Dashboard ---
  console.log('Recording Scene 2: Reviewer Login & Dashboard...');
  await nextBtn.click();
  await page.waitForTimeout(1000);
  const projectCard = page.locator('[data-testid="project-card"]').first();
  if (await projectCard.isVisible()) {
    await projectCard.hover();
  }
  await page.waitForTimeout(3500);

  // --- SCENE 3: Official Rubric Scorecard & Safety Invariants ---
  console.log('Recording Scene 3: Official Rubric Scorecard...');
  await nextBtn.click();
  await page.waitForTimeout(1500);
  // Scroll down smoothly to show the 12 criteria
  await page.mouse.wheel(0, 300);
  await page.waitForTimeout(2000);
  await page.mouse.wheel(0, -300);
  await page.waitForTimeout(2000);

  // --- SCENE 4: Triggering Multi-Agent Analysis ---
  console.log('Recording Scene 4: Triggering Multi-Agent Analysis...');
  await nextBtn.click();
  await page.waitForTimeout(1500);
  // Modal should be visible
  await page.waitForTimeout(3500);

  // --- SCENE 5: AI Mentor Chat & Milestones ---
  console.log('Recording Scene 5: AI Mentor Chat & Milestones...');
  await nextBtn.click();
  await page.waitForTimeout(2000);
  // Scroll slightly in mentor tab
  await page.mouse.wheel(0, 200);
  await page.waitForTimeout(3000);

  // --- SCENE 6: Phase 4 On-Call Diagnostics & Observability ---
  console.log('Recording Scene 6: Observability & On-Call...');
  await nextBtn.click();
  await page.waitForTimeout(2000);
  await page.mouse.wheel(0, 250);
  await page.waitForTimeout(3000);

  // --- SCENE 7: Architecture, Single-Command Setup & Wrap-Up ---
  console.log('Recording Scene 7: Architecture & Wrap-Up...');
  await nextBtn.click();
  await page.waitForTimeout(4000);

  // Close page to flush video recording
  const video = page.video();
  await page.close();

  if (video) {
    const videoPath = await video.path();
    const demoDir = path.resolve(process.cwd(), '../demo');
    if (!fs.existsSync(demoDir)) fs.mkdirSync(demoDir, { recursive: true });

    const targetPath = path.resolve(demoDir, 'devtrack_ai_demo.webm');
    fs.copyFileSync(videoPath, targetPath);
    console.log(`\nDemo video saved successfully: ${targetPath} (${fs.statSync(targetPath).size} bytes)`);
  }
});
