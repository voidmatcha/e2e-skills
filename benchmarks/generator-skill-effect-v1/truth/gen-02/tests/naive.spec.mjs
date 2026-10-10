import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists to measure headroom, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("filters products", async ({ page }) => {
  await page.fill("#ps-query", "Jacket");
  await expect(page.getByText("Alpine Jacket")).toBeVisible();
  await expect(page.getByText("Camp Mug")).not.toBeVisible();
});

test("clear shows everything again", async ({ page }) => {
  await page.fill("#ps-query", "Jacket");
  await page.click("#ps-clear");
  await expect(page.getByText("Camp Mug")).toBeVisible();
});
