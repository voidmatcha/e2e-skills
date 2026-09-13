// confirmation-case: SMOKE-CFV-01/tests/orchestra-call.spec.ts
import { test } from '@playwright/test';
test('records orchestra call', async ({ page }) => {
  await page.goto('/rehearsals/orchestra-call');
  await page.getByTestId('call-recorded').isVisible();
});
