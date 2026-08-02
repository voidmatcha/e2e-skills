import { test, expect } from '@playwright/test';

test('uses the dark theme', async ({ page }) => {
  await page.goto('/theme');
  await expect.poll(
    async () => page.evaluate(
      () => getComputedStyle(document.body).getPropertyValue('--theme-name'),
    ),
  ).toBe('dark');
});

test('opens the member area', async ({ page }) => {
  await page.goto('/member');
  await expect(page.getByRole('heading', { name: 'Member overview', exact: true })).toBeVisible();
});

test('closes the visible drawer', async ({ page }) => {
  await page.goto('/theme');
  const drawer = page.getByTestId('drawer');
  await expect(drawer).toBeVisible();
  await page.getByRole('button', { name: 'Close drawer', exact: true }).click();
  await expect(drawer).toBeHidden();
});
