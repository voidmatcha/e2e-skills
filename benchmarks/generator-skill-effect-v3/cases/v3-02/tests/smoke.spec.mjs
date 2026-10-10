import { expect, test } from "@playwright/test";

test("shows the recipes heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Recipes" })).toBeVisible();
});
