import { expect, test } from "@playwright/test";

test("shows the product list heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Products" })).toBeVisible();
});
