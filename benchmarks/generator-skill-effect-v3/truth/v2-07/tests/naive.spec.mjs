import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("opens a message", async ({ page }) => {
  await page.click("#ib-list li:nth-child(1) button");
  await expect(page.locator("#ib-body")).toBeVisible();
  await expect(page.locator("#ib-heading")).toHaveText("Inbox (2)");
});

test("filters unread", async ({ page }) => {
  await page.check("#ib-unread-only");
  await expect(page.locator("#ib-list li")).toHaveCount(3);
});
