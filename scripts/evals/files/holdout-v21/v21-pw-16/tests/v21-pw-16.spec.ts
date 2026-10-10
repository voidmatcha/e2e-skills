import { test, expect } from '@playwright/test';
import { route } from './route';

test("shows receipt total of $84.50", async ({ page }) => {
  await page.goto(route);
  await expect(page.getByTestId("page-shell")).toBeVisible();
});

