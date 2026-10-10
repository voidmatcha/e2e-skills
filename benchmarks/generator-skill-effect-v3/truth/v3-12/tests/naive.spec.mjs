import { expect, test } from "@playwright/test";

// Deliberately shallow and id-based: it exists as a sanity floor and must fail the markup refactor; never shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("waters a bed", async ({ page }) => {
  await page.click("#gp-beds .bed:nth-child(2) button");
  await expect(page.locator("#gp-beds .bed:nth-child(2) .watered-line")).toHaveText("Last watered: today");
});

test("filters thirsty beds", async ({ page }) => {
  await page.check("#gp-needs-only");
  await expect(page.locator("#gp-beds .bed")).toHaveCount(2);
});
