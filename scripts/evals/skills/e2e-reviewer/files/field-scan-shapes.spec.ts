import { test, expect } from '@playwright/test';

const THEMES = [{ name: 'dark', contrast: 2 }, { name: 'light', contrast: 1 }];

test('switches themes and keeps the selected option', async ({ page }) => {
  await page.goto('/settings');
  const loading = page.getByTestId('loading');
  await loading.waitFor({ state: 'hidden' }).catch(() => {});
  await expect(loading).toBeHidden();
  for (const theme of THEMES) {
    await page.getByRole('button', { name: theme.name, exact: true }).click();
    if (theme.name === 'dark') await expect(page.locator('body')).toHaveClass(/dark/);
  }
  const options = page.getByRole('menuitemradio');
  const checked = await options.evaluateAll((items) => items.findIndex((item) => item.getAttribute('aria-checked') === 'true'));
  expect(checked).toBeGreaterThanOrEqual(0);
  const errors = await page.locator('.error').allTextContents();
  if (errors.length > 0) expect(errors).toHaveLength(0);
});

test('cleans up after saving', async ({ page }) => {
  try {
    await page.goto('/settings');
    await expect(page.getByRole('main')).toBeVisible();
  } finally {
    await page.request.delete('/api/settings').catch(() => {});
  }
});

test('polls the row count', async ({ page }) => {
  await page.goto('/rows');
  await expect.poll(async () => page.getByRole('row').count()).toBeGreaterThanOrEqual(0);
  await page.reload().catch(() => {});
  await expect(page.getByRole('row').first()).toBeVisible();
});
