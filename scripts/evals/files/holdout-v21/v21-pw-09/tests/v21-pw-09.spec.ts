import { test, expect } from '@playwright/test';

test("closes the billing modal", async ({ page }) => {
  await page.goto("/billing");
  await expect(page.getByTestId("billing-modal")).toBeVisible();
  await page.getByTestId("Close").click();
});

