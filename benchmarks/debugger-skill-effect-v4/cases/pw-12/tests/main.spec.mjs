
import { test, expect } from "@playwright/test";

test("the list has three entries", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#list li")).toHaveCount(3);
});

test("the list is alphabetical, starting with Apple", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#list li").first()).toHaveText("Apple");
});
