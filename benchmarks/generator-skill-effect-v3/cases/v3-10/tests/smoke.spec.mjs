import { expect, test } from "@playwright/test";

test("shows the order heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Order #48213" })).toBeVisible();
});
