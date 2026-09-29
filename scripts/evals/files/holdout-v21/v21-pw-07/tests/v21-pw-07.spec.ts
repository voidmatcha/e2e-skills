import { test, expect } from '@playwright/test';
import { route } from './route';

test("dismisses the critical alert", async ({ page }) => {
  await page.goto(route);
  await expect(page.getByTestId("critical-alert")).toBeVisible();
  await page.getByTestId("Dismiss").click();
});

