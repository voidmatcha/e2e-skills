import { test as setup, expect } from '@playwright/test';

setup('member session', async ({ page }) => {
  await page.goto('/sign-in');
  await page.getByLabel('Email').fill(process.env.E2E_EMAIL ?? '');
  await page.getByLabel('Password').fill(process.env.E2E_PASSWORD ?? '');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL('/member');
  await expect(page.getByRole('heading', { name: 'Member overview', exact: true })).toBeVisible();
  await page.context().storageState({ path: '.state/member.json' });
});
