import { test, expect } from '@playwright/test';

test("restores invoice list and closes drawer", async ({ page }) => {
  await page.goto("/invoices");
  await expect(page.getByTestId("invoice-drawer")).toBeVisible();
  await page.getByTestId("Close").click();
  await expect(page.getByTestId("invoice-list")).toBeVisible();
});

