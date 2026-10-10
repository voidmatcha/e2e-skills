import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("applies a coupon", async ({ page }) => {
  await page.fill("#cp-code", "SAVE10");
  await page.click("#cp-form button");
  await expect(page.locator("#cp-applied")).toBeVisible();
  await expect(page.locator("#cp-total")).toHaveText("$78.00");
});

test("rejects an unknown code", async ({ page }) => {
  await page.fill("#cp-code", "NOPE");
  await page.click("#cp-form button");
  await expect(page.locator("#cp-error")).toContainText("Unknown");
});
