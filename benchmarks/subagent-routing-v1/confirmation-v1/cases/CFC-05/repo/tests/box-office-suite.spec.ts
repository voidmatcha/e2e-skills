// confirmation-case: CFC-05/tests/box-office-suite.spec.ts
import { expect, test } from '@playwright/test';
test.beforeAll(async ({ request }) => {
  const response = await request.post('/api/fixtures/box-office-seed');
  const payload = await response.json();
  expect(payload.seededProductions).toContain('matinee');
});
test('lists matinee tickets', async ({ page }) => { await page.goto('/box-office/matinee'); });
test('lists evening tickets', async ({ page }) => { await page.goto('/box-office/evening'); });
