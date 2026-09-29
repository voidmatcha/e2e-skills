import { test, expect } from '@playwright/test';
import { route } from './route';

test("shows Ancient Maps and Room B on the museum page", async ({ page }) => {
  await page.goto(route);
  await expect(page.getByTestId("exhibit-title")).toHaveText("Ancient Maps");
});

test("restores museum list and closes panel", async ({ page }) => {
  await page.goto(route + '?panel=open');
  await expect(page.getByTestId("exhibit-panel")).toBeVisible();
  await page.getByTestId("Close exhibit").click();
  await expect(page.getByTestId("exhibit-list")).toBeVisible();
});

