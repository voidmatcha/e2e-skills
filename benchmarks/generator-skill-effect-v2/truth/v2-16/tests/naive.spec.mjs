import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("completes the quiz", async ({ page }) => {
  await page.check("#q1-1");
  await page.click("#qz-next");
  await page.check("#q2-2");
  await page.click("#qz-next");
  await page.check("#q3-0");
  await page.click("#qz-submit");
  await expect(page.locator("#qz-score")).toContainText("You scored");
});
