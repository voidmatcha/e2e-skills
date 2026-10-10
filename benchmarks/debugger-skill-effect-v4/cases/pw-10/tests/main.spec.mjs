
import { test, expect } from "@playwright/test";

test.describe("inventory", () => {
  test.beforeEach(async ({ request, page }) => {
    await request.post("/api/seed");
    await page.goto("/");
  });

  test("lists the seeded bolt", async ({ page }) => {
    await expect(page.locator("#items li", { hasText: "bolt" })).toBeVisible();
  });

  test("lists the seeded nut", async ({ page }) => {
    await expect(page.locator("#items li", { hasText: "nut" })).toBeVisible();
  });

  test("shows the item count", async ({ page }) => {
    await expect(page.locator("#count")).toHaveText("3 items");
  });
});
