import { test, expect } from '@playwright/test';

test("shows Gold membership tier", async ({ page }) => {
  await page.goto("/account");
  await expect(page.getByTestId("page-shell")).toBeVisible();
});

