import { expect, test } from "@playwright/test";

test("shows titles", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#rt-list")).toContainText("North");
  await expect(page.locator("#rt-list")).toContainText("South");
});
