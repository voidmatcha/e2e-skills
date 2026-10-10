import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("saves an address", async ({ page }) => {
  await page.selectOption("#ab-country", "US");
  await page.selectOption("#ab-region", "Texas");
  await page.fill("#ab-postal", "73301");
  await page.click("#ab-form button");
  await expect(page.locator("#ab-list")).toContainText("Texas");
});

test("rejects a bad postal code", async ({ page }) => {
  await page.selectOption("#ab-country", "US");
  await page.selectOption("#ab-region", "Texas");
  await page.fill("#ab-postal", "abc");
  await page.click("#ab-form button");
  await expect(page.locator("#ab-error")).toContainText("valid postal code");
});
