import { expect, test } from "@playwright/test";

test("shows the discussion heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Discussion" })).toBeVisible();
});
