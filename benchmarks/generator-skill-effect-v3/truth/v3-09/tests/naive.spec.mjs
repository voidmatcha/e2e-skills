import { expect, test } from "@playwright/test";

// Deliberately shallow and id-based: it exists as a sanity floor and must fail the markup refactor; never shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("studies a deck", async ({ page }) => {
  await page.click("#fc-decks .deck:nth-child(2) button");
  await expect(page.locator("#fc-study")).toBeVisible();
  await expect(page.locator("#fc-front")).toHaveText("Norway");
  await page.click("#fc-flip");
  await expect(page.locator("#fc-back")).toHaveText("Oslo");
  await page.click("#fc-got");
  await page.click("#fc-got");
  await expect(page.locator("#fc-done")).toBeVisible();
});
