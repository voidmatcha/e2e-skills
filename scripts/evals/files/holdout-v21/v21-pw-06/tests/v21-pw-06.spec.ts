import { test, expect } from '@playwright/test';

test("restores help page and closes overlay", async ({ page }) => {
  await page.goto("/help");
  await expect(page.getByTestId("help-overlay")).toBeVisible();
  await page.getByTestId("Done").click();
  await expect(page.getByTestId("help-page")).toBeVisible();
});

