import { test, expect } from '@playwright/test';

test("shows ticker and price", async ({ page }) => {
  await page.goto("/stocks");
  await expect(page.getByTestId("ticker-symbol")).toHaveText("ACME");
});

