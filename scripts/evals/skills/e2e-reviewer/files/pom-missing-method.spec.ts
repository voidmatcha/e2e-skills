import { expect, test } from '@playwright/test';
import { NotificationSettingsPage } from './pages/notification-settings-page';

test('changes the digest frequency', async ({ page }) => {
  const settings = new NotificationSettingsPage(page);
  await settings.open();
  await page.getByLabel('Digest frequency').selectOption('weekly');
  await expect(page.getByLabel('Digest frequency')).toHaveValue('weekly');
});

test('looks up a public incident on a page with no POM', async ({ page }) => {
  await page.goto('/incident-lookup');
  await page.getByLabel('Incident ID').fill('INC-2048');
  await page.getByRole('button', { name: 'Find incident' }).click();
  await expect(page.getByTestId('incident-result')).toContainText('INC-2048');
});
