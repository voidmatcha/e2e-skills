import { test, expect } from '@playwright/test';

test('saves the selected locale', async ({ page }) => {
  await page.goto('/preferences');
  await page.selectOption('#locale', 'ko-KR');
  const panel = page.getByTestId('preference-panel');
  await expect.soft(panel).toBeVisible();
  await panel.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByTestId('locale')).toHaveText('ko-KR');
});
