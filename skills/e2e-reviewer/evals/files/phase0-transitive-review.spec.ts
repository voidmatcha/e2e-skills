import { expect, test } from './phase0-transitive-barrel';

test.only('shows the saved state', async ({ page }) => {
  await page.goto('/settings');
  await expect(page.getByText('Saved')).toBeVisible();
});
