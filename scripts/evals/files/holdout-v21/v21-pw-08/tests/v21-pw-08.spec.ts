import { test, expect } from '@playwright/test';

test("removes the cart item", async ({ page }) => {
  await page.goto("/cart");
  await expect(page.getByTestId("cart-item")).toBeVisible();
  await page.getByTestId("Remove item").click();
});

