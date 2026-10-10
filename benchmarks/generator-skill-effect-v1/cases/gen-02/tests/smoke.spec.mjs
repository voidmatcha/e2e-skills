import { expect, test } from "@playwright/test";

test("shows the products heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Products" })).toBeVisible();
});
