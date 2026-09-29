import { test, expect } from '@playwright/test';

test.use({ viewport: { width: 800, height: 600 }, deviceScaleFactor: 1 });

test('matches the approved warning icon artwork', async ({ page }) => {
  await page.goto('/design/status-icons?state=warning');
  await expect(page.getByTestId('status-icon')).toHaveScreenshot('warning-icon.png', { maxDiffPixels: 900 });
});

test('matches the approved plan card layout', async ({ page }) => {
  await page.goto('/design/plan-card');
  await expect(page.getByTestId('plan-card')).toHaveScreenshot('plan-card.png', { maxDiffPixels: 40 });
});
