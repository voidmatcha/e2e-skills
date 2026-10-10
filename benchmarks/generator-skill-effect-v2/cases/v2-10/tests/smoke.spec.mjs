import { expect, test } from "@playwright/test";

test("shows the inventory heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Inventory" })).toBeVisible();
});
