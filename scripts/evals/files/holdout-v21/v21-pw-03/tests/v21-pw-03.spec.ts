import { test, expect } from '@playwright/test';

test("shows current rates and hides history", async ({ page }) => {
  await page.goto("/shipping");
  await expect(page.getByTestId("shipping-history")).toBeVisible();
  await page.getByTestId("Current rates").click();
  await expect(page.getByTestId("current-rates")).toBeVisible();
});

