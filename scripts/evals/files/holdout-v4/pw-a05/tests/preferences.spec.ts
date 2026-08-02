import { test, expect } from '@playwright/test';
import { PreferencesPage } from '../pages/preferences-page';

test('saves the selected locale', async ({ page }) => {
  const preferences = new PreferencesPage(page);
  await preferences.open();
  await page.selectOption('#locale', 'ko-KR');
  const panel = page.getByTestId('preference-panel');
  await expect.soft(panel).toBeVisible();
  await panel.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByTestId('locale')).toHaveText('ko-KR');
});
