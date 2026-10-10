import { expect, test } from "@playwright/test";

test("shows the orders heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Orders" })).toBeVisible();
});
