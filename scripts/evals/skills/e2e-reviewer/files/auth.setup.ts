import { test as setup } from '@playwright/test';

// Runs as the `setup` project (playwright.config lists it as a dependency of the member
// projects), regenerating the admin session programmatically on every run — fresh clones
// and CI never depend on a manually captured file.
setup('authenticate admin', async ({ page }) => {
  await page.goto(`/api/test-auth/login?token=${process.env.ADMIN_API_TOKEN}`);
  await page.waitForURL('**/dashboard');
  await page.context().storageState({ path: '.auth/admin.json' });
});
