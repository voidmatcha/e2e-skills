import { expect, test } from "@playwright/test";

// Deliberately shallow and id-based: it exists as a sanity floor and must fail the markup refactor; never shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("advances the order", async ({ page }) => {
  await page.click("#ot-advance");
  await expect(page.locator("#ot-steps li:nth-child(2) .step-status")).toHaveText("Current");
});

test("cancels the order", async ({ page }) => {
  await page.click("#ot-cancel");
  await expect(page.locator("#ot-cancelled")).toBeVisible();
});
