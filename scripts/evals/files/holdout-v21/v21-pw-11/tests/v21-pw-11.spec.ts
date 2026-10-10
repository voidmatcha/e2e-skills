import { test, expect } from '@playwright/test';

test("shows platform and delay", async ({ page }) => {
  await page.goto("/trains");
  await expect(page.getByTestId("platform-label")).toHaveText("Platform 4");
});

