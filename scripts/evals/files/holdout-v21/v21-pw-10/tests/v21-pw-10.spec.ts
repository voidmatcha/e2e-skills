import { test, expect } from '@playwright/test';
import { route } from './route';

test("shows rain forecast and temperature", async ({ page }) => {
  await page.goto(route);
  await expect(page.getByTestId("forecast-heading")).toHaveText("Rain tomorrow");
});

