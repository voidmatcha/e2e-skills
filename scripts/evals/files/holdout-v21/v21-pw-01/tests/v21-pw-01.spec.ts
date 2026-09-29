import { test, expect } from '@playwright/test';
import { route } from './route';

test("restores profile summary and dismisses editor", async ({ page }) => {
  await page.goto(route);
  await expect(page.getByTestId("edit profile")).toBeVisible();
  await page.getByTestId("Cancel").click();
  await expect(page.getByTestId("profile-summary")).toBeVisible();
});

