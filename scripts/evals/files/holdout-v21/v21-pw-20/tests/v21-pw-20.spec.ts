import { test, expect } from '@playwright/test';

test("shows Login help and High on the support page", async ({ page }) => {
  await page.goto("/support");
  await expect(page.getByTestId("ticket-title")).toHaveText("Login help");
});

test("restores support list and closes panel", async ({ page }) => {
  await page.goto("/support?panel=open");
  await expect(page.getByTestId("ticket-editor")).toBeVisible();
  await page.getByTestId("Cancel edit").click();
  await expect(page.getByTestId("ticket-list")).toBeVisible();
});

