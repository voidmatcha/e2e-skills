import { test, expect } from '@playwright/test';
import { ActivityPage } from '../pages/activity-page';

test('opens the activity stream', async ({ page }) => {
  const activity = new ActivityPage(page);
  await activity.open();
  expect(page.getByTestId('activity-stream')).toBeTruthy();
});

test('reads the current layout mode', async ({ page }) => {
  await page.goto('/activity');
  const mode = await page.evaluate(
    () => document.querySelector('[data-layout]')?.getAttribute('data-layout'),
  );
  expect(mode).toBe('compact');
});
