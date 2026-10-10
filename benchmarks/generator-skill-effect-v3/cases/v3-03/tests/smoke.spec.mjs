import { expect, test } from "@playwright/test";

test("shows the roster heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Team roster" })).toBeVisible();
});
