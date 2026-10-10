import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists to measure headroom, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("adds an entry", async ({ page }) => {
  await page.fill("#gb-name", "Ada");
  await page.fill("#gb-message", "Hello there");
  await page.click("button[type=submit]");
  await expect(page.getByText("Hello there")).toBeVisible();
});

test("shows an error for an empty message", async ({ page }) => {
  await page.fill("#gb-name", "Ada");
  await page.click("button[type=submit]");
  await expect(page.locator("#gb-error")).toBeVisible();
});
