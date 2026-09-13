// confirmation-case: CFV-05/tests/transmitter.spec.ts
import { expect, test } from '@playwright/test';

test('shows transmitter status', async ({ page }) => {
  await page.goto('/production/transmitter');
  await expect(page.getByTestId('transmitter-status')).toContainText('On air');
});
