import { expect, test } from "@playwright/test";

test("shows the profile heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Profile" })).toBeVisible();
});
