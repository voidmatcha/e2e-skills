import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists to measure headroom, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("subscribes", async ({ page }) => {
  await page.fill("#nl-email", "ada@example.com");
  await page.click("#nl-subscribe");
  await expect(page.locator("#nl-success")).toBeVisible();
  await expect(page.getByText("1 subscriber")).toBeVisible();
});
