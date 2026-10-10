
import { test, expect } from "@playwright/test";

test("the offer text is present", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#banner")).toHaveText("Free shipping today");
});

test("the offer banner becomes fully visible", async ({ page }) => {
  await page.goto("/");
  await page.click("#show");
  const opacity = await page.locator("#banner").evaluate((el) => getComputedStyle(el).opacity);
  expect(opacity).toBe("1");
});
