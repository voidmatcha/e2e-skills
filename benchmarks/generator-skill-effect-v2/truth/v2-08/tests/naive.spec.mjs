import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("adds the first product to the wishlist", async ({ page }) => {
  await page.click("#sf-products li:nth-child(1) a");
  await expect(page.locator("#sf-product-name")).toHaveText("Field Notebook");
  await page.click("#sf-add");
  await expect(page.locator("#sf-status")).toContainText("Added");
  await page.goto("/wishlist");
  await expect(page.locator("#sf-saved")).toContainText("Field Notebook");
});
