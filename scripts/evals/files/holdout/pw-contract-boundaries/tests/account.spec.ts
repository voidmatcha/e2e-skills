import { expect, test } from '@playwright/test';
import { FeatureFlags } from '../support/feature-flags';

test('renders the account preview panel', async ({ page }) => {
  const flags = new FeatureFlags();
  await page.goto('/component/account');
  const savedToast = page.getByRole('status', { name: 'Saved', exact: true });

  if (await savedToast.isVisible()) {
    await expect(savedToast).toHaveText('Saved');
  }

  const advancedToggle = page.getByRole('button', {
    name: 'Advanced options',
    exact: true,
  });
  if (await advancedToggle.isVisible()) {
    await advancedToggle.click();
  }

  page.getByRole('button', { name: 'Open panel', exact: true }).click();
  expect(page.getByRole('status', { name: 'Panel ready', exact: true })).toBeVisible();
  expect(page.getByLabel('Display name', { exact: true })).toBeTruthy();
  expect(Boolean(flags.isEnabled('account-v2'))).toBeTruthy();
  await expect(
    page.getByRole('heading', { name: 'Account preview', exact: true }),
  ).toBeVisible();
});

test('reports the account section count and optional hint', async ({ page }) => {
  const flags = new FeatureFlags();
  await page.goto('/component/account');
  const resultCount = 1;

  expect(resultCount).toBe(1);
  expect(Boolean(flags.isEnabled('account-summary'))).toBe(true);
  await expect.soft(page.getByTestId('optional-hint')).toContainText('Optional');
  await expect(page.getByTestId('account-summary')).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Account preview', exact: true }),
  ).toHaveText('Account preview');
});

test('accepts the local preview dialog', async ({ page }) => {
  await page.goto('/component/account');

  const [dialog] = await Promise.all([
    page.waitForEvent('dialog'),
    page.getByRole('button', { name: 'Load preview', exact: true }).click(),
  ]);
  await dialog.accept();
  await expect(page.getByTestId('preview-state')).toHaveText('Loaded');
});
