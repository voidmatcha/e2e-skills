import { expect, test } from "@playwright/test";

test("shows verification statuses", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#primary-status")).toBeVisible();
  await expect(page.locator("#secondary-status")).toBeVisible();
});
