import { expect, test as setup } from '@playwright/test';

setup('creates admin state', async ({ page }) => {
  await page.goto('/test-login');
  await expect(page.getByRole('heading', { name: 'Test login' })).toBeVisible();
  await page.context().storageState({ path: '.auth/admin.json' });
});
