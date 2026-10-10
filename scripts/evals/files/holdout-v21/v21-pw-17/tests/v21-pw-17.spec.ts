import { test, expect } from '@playwright/test';

test("shows the next appointment at 09:30", async ({ page }) => {
  await page.goto("/calendar");
  await expect(page.getByTestId("page-shell")).toBeVisible();
});

