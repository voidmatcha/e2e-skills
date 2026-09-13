// confirmation-case: CFV-01/tests/live-segment.spec.ts
import { test } from '@playwright/test';

test('publishes the matinee segment', async ({ page }) => {
  await page.goto('/box-office/matinee');
  await page.getByRole('button', { name: 'Publish segment' }).click();
  await page.getByTestId('segment-live').isVisible();
});
