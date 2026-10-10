import { expect, test } from "@playwright/test";

// Deliberately shallow and id-based: it exists as a sanity floor and must fail the markup refactor; never shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("toggles leave", async ({ page }) => {
  await page.click("#tr-rows tr:nth-child(1) button:nth-of-type(1)");
  await expect(page.locator("#tr-rows tr:nth-child(1) .badge")).toHaveText("On leave");
});

test("removes a member", async ({ page }) => {
  await page.click("#tr-rows tr:nth-child(2) button:nth-of-type(2)");
  await page.click("#tr-rows tr.confirm button:nth-of-type(1)");
  await expect(page.locator("#tr-rows tr.member")).toHaveCount(4);
});
