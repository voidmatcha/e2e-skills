// confirmation-case: CFC-01/tests/cast-banner.spec.ts
import { expect, test } from '@playwright/test';
test('shows the understudy notice', async ({ page }) => {
  await page.goto('/cast?understudy=false');
  await expect(page.getByTestId('understudy-banner')).toBeVisible();
});
