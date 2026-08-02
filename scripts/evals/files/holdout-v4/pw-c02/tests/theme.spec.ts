import { test, expect } from '@playwright/test';

test('uses the dark theme', async ({ page }) => {
  await page.goto('/theme');
  const theme = await page.evaluate(
    () => getComputedStyle(document.body).getPropertyValue('--theme-name'),
  );
  expect(theme).toBe('dark');
});

test('opens the member area', async ({ page }) => {
  await page.goto('/member');
  await expect(page.getByRole('heading', { name: 'Member overview' })).toBeVisible();
});

test('checks whether the drawer is visible', async ({ page }) => {
  await page.goto('/theme');
  const visible = await page.getByTestId('drawer').isVisible();
  expect(visible).toBe(false);
});
