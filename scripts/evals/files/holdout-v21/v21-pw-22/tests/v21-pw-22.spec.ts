import { test, expect } from '@playwright/test';
import { route } from './route';

test("restores playlist and closes editor", async ({ page }) => {
  await page.goto(route);
  await expect(page.getByTestId("playlist-editor")).toBeVisible();
  await page.getByTestId("Cancel").click();
  await expect(page.getByTestId("playlist-summary")).toBeVisible();
  await expect(page.getByTestId("playlist-editor")).toBeHidden();
});

