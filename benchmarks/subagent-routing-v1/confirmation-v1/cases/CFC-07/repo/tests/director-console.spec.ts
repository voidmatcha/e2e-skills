// confirmation-case: CFC-07/tests/director-console.spec.ts
import { expect, test } from '@playwright/test';
test.use({ storageState: '.auth/expired-director.json' });
test('shows director console', async ({ page }) => {
  await page.goto('/production/director-console');
  await expect(page.getByTestId('director-controls')).toBeVisible();
});
