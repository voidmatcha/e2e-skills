import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("places an order", async ({ page }) => {
  await page.fill("#co-name", "Ada");
  await page.fill("#co-street", "1 Way");
  await page.fill("#co-city", "Springfield");
  await page.click("#co-address-form button");
  await page.click("#co-method-next");
  await expect(page.locator("#co-total")).toContainText("Total");
  await page.click("#co-confirm");
  await expect(page.locator("#co-confirmation")).toContainText("confirmed");
});

test("shows a declined payment", async ({ page }) => {
  await page.fill("#co-name", "Ada");
  await page.fill("#co-street", "1 Way");
  await page.fill("#co-city", "Failville");
  await page.click("#co-address-form button");
  await page.click("#co-method-next");
  await page.click("#co-confirm");
  await expect(page.locator("#co-error")).toContainText("Payment declined");
});
