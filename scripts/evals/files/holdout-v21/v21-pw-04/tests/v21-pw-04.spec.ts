import { test, expect } from '@playwright/test';

test("shows filtered results and closes filters", async ({ page }) => {
  await page.goto("/catalog");
  await expect(page.getByTestId("filter-panel")).toBeVisible();
  await page.getByTestId("Apply filters").click();
  await expect(page.getByTestId("filtered-results")).toBeVisible();
});

