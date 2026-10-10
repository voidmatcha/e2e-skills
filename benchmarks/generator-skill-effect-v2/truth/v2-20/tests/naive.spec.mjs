import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("loads more", async ({ page }) => {
  await page.click("#rl-more");
  await expect(page.getByText("Article 15", { exact: true })).toBeVisible();
});

test("marks as read", async ({ page }) => {
  await page.click("#rl-list li:nth-child(1) button");
  await expect(page.locator("#rl-list li:nth-child(1) button")).toHaveText("Mark as unread");
});
