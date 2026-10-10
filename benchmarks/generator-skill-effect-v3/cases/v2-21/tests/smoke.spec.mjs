import { expect, test } from "@playwright/test";

test("shows the release notes heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Release notes" })).toBeVisible();
});
