import { test, expect } from '@playwright/test';

test('changes the time zone', async ({ page }) => {
  await page.goto('/member/settings');
  await page.locator('#timezone').selectOption('Asia/Seoul');
  await expect.soft(page.getByTestId('timezone')).toHaveText('Asia/Seoul');
  await expect(page.getByTestId('save-state')).toHaveText('Saved');
});
