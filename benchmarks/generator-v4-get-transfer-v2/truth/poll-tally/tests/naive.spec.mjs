import { expect, test } from "@playwright/test";

test("shows poll choices", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#vote-list")).toContainText("Ruby");
  await expect(page.locator("#vote-list")).toContainText("Blue");
});
