import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists to measure headroom, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("adds a product to the cart", async ({ page }) => {
  await page.click("#ct-products li:nth-child(1) button");
  await expect(page.locator("#ct-lines")).toContainText("Canvas Tote");
  await expect(page.locator("#ct-total")).toHaveText("Total: $25.00");
});

test("removes a product", async ({ page }) => {
  await page.click("#ct-products li:nth-child(1) button");
  await page.click("#ct-lines li:nth-child(1) button:last-child");
  await expect(page.locator("#ct-lines")).not.toContainText("Canvas Tote");
});
