import { expect, test } from "@playwright/test";

test("shows the preferences heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Preferences" })).toBeVisible();
});
