import { test, expect } from '@playwright/test';

test("shows home and away scores", async ({ page }) => {
  await page.goto("/scores");
  await expect(page.getByTestId("home-score")).toHaveText("3");
});

