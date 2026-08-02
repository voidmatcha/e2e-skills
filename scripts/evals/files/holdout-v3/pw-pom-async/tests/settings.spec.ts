import { expect, test } from '@playwright/test';
import { SettingsPage } from '../pages/settings-page';

test('updates regional settings', async ({ page }) => {
  const settings = new SettingsPage(page);
  await settings.open();
  await page.getByLabel('Currency').selectOption('KRW');
  await expect(page.getByLabel('Currency')).toHaveValue('KRW');
  const saved = page.getByRole('status', { name: 'Saved settings' });
  expect(saved).toBeVisible();
  const reload = page.getByRole('button', { name: 'Reload preferences' });
  reload.click();
});

test('accepts a cookie banner outside settings ownership', async ({ page }) => {
  const settings = new SettingsPage(page);
  await settings.open();
  await page.getByRole('button', { name: 'Accept cookies' }).click();
  await expect(page.getByRole('button', { name: 'Accept cookies' })).toBeHidden();
  await settings.setCurrency('USD');
  await expect(page.getByLabel('Currency')).toHaveValue('USD');
});

test('checks a synchronous aggregate', async ({ page }) => {
  await page.goto('/settings');
  const selected = await page.locator('option:checked').count();
  expect(selected).toBe(1);
});

test('submits two independent actions together', async ({ page }) => {
  await page.goto('/settings');
  await Promise.all([
    page.getByRole('button', { name: 'Save' }).click(),
    page.waitForURL('/settings?stored=true'),
  ]);
  await expect(page).toHaveURL('/settings?stored=true');
});
