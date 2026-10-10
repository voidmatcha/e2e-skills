import { test, expect } from '@playwright/test';

test('switching to activity shows activity and hides overview', async ({ page }) => {
  await page.goto('/account');
  await expect(page.getByRole('tabpanel', { name: 'Overview' })).toBeVisible();
  await page.getByRole('tab', { name: 'Activity' }).click();
  await expect(page.getByRole('tabpanel', { name: 'Activity' })).toBeVisible();
  await expect(page.getByRole('tabpanel', { name: 'Overview' })).toBeHidden();
});
