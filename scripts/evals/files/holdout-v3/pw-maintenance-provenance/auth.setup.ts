import { test as setup } from '@playwright/test';

setup('writes generated admin state', async ({ page }) => {
  await page.goto('/test-login');
  await page.context().storageState({ path: '.auth/admin-generated.json' });
});
