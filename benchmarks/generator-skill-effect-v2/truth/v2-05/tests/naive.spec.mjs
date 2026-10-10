import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("books a slot", async ({ page }) => {
  await page.click("#bk-slots li:nth-child(1) button");
  await expect(page.locator("#bk-mine")).toContainText("09:00");
});

test("cancels a booking", async ({ page }) => {
  await page.click("#bk-slots li:nth-child(1) button");
  await page.click("#bk-mine li button");
  await expect(page.locator("#bk-mine li")).toHaveCount(0);
});
