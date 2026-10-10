import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("adds an expense", async ({ page }) => {
  await page.fill("#ex-description", "Coffee");
  await page.fill("#ex-amount", "3.5");
  await page.click("#ex-form button");
  await expect(page.locator("#ex-list")).toContainText("$3.50");
  await expect(page.locator("#ex-total")).toHaveText("Total: $3.50");
});

test("rejects a bad amount", async ({ page }) => {
  await page.fill("#ex-description", "Taxi");
  await page.fill("#ex-amount", "-1");
  await page.click("#ex-form button");
  await expect(page.locator("#ex-amount-error")).toBeVisible();
});
