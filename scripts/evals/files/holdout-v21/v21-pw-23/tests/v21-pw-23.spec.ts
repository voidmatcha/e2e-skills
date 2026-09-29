import { test, expect } from '@playwright/test';

test("restores orders and closes drawer", async ({ page }) => {
  await page.goto("/orders");
  await expect(page.getByTestId("order-drawer")).toBeVisible();
  await page.getByTestId("Close").click();
  await expect(page.getByTestId("order-list")).toBeVisible();
  await expect(page.getByTestId("order-drawer")).toBeHidden();
});

