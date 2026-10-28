import { test, expect } from '@playwright/test';

// .auth/member.json comes from docs/capture-session.md: a developer logs in locally and
// copies the storage JSON out of DevTools by hand. Nothing in the repo regenerates it.
test.describe('member billing', () => {
  test.use({ storageState: '.auth/member.json' });

  test('member sees the billing page', async ({ page }) => {
    await page.goto('/billing');
    await expect(page.getByRole('heading', { name: 'Billing' })).toBeVisible();
  });
});

// .auth/admin.json is written by auth.setup.ts on every run (the `setup` project) —
// a programmatic producer exists, so this dependency is reproducible.
test.describe('admin audit log', () => {
  test.use({ storageState: '.auth/admin.json' });

  test('admin sees the audit log', async ({ page }) => {
    await page.goto('/admin/audit');
    await expect(page.getByRole('heading', { name: 'Audit log' })).toBeVisible();
  });
});
