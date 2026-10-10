import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("adds and removes a tag", async ({ page }) => {
  await page.fill("#tg-input", "node");
  await page.press("#tg-input", "Enter");
  await expect(page.locator("#tg-chips")).toContainText("node");
  await page.click("#tg-chips li button");
  await expect(page.locator("#tg-chips li")).toHaveCount(0);
});

test("saves", async ({ page }) => {
  await page.fill("#tg-input", "node");
  await page.press("#tg-input", "Enter");
  await page.click("#tg-save");
  await expect(page.locator("#tg-status")).toContainText("saved");
});
