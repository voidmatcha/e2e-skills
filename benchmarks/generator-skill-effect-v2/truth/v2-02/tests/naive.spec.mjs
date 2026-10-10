import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("searches", async ({ page }) => {
  await page.fill("#ls-query", "Alice");
  await expect(page.getByText("Alice in Wonderland")).toBeVisible();
  await expect(page.locator("#ls-recent")).toContainText("Alice");
});
