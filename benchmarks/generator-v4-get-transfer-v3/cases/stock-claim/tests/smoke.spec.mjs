import { expect, test } from "@playwright/test";

test("shows stock to claim", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Stock claim" })).toBeVisible();
});
