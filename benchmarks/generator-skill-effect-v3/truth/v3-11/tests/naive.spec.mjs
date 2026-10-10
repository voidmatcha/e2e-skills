import { expect, test } from "@playwright/test";

// Deliberately shallow and id-based: it exists as a sanity floor and must fail the markup refactor; never shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("sends a message", async ({ page }) => {
  await page.fill("#th-input", "Hello");
  await page.click("#th-send");
  await expect(page.locator("#th-messages .message").last()).toContainText("Hello");
});

test("marks as read", async ({ page }) => {
  await page.click("#th-mark-read");
  await expect(page.locator("#th-messages .divider")).toHaveCount(0);
});
