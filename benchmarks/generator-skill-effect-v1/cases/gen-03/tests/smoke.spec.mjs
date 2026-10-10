import { expect, test } from "@playwright/test";

test("shows the shop heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Shop" })).toBeVisible();
});
