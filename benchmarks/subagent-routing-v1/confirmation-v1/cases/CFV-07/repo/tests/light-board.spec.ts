// confirmation-case: CFV-07/tests/light-board.spec.ts
import { expect, test } from '@playwright/test';
test('shows channels', async ({ page }) => {
  await page.goto('/production/light-board');
  await expect(page.getByTestId('channel-count')).toHaveText('24');
});
