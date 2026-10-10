import { expect, test } from "@playwright/test";

test("shows the shopping list heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Shopping list" })).toBeVisible();
});
