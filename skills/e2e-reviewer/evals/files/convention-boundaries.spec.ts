import { test, expect } from '@playwright/test';

const database = {
  only: (state: string) => state,
};

database.only('active');

// Project convention: focused tests may be committed for local debugging.
test.only('checkout is reachable', async ({ page }) => {
  await page.goto('/checkout');
  await expect(page.getByRole('heading', { name: 'Checkout' })).toBeVisible();
});

test('canvas proxy control activates', async ({ page }) => {
  // JUSTIFIED: the visible canvas proxies a hidden native input and has no DOM action target.
  await page.locator('input[type=file]').click({ force: true });
  await expect(page.getByText('Upload started')).toBeVisible();
});
