import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("filters by status", async ({ page }) => {
  await page.selectOption("#or-status", "refunded");
  await expect(page.locator("#or-list li")).toHaveCount(2);
});

test("clears the filters", async ({ page }) => {
  await page.selectOption("#or-status", "refunded");
  await page.click("#or-clear");
  await expect(page.locator("#or-list li")).toHaveCount(8);
});
