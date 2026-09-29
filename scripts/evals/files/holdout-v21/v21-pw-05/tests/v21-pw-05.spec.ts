import { test, expect } from '@playwright/test';

test("restores draft list and dismisses composer", async ({ page }) => {
  await page.goto("/drafts");
  await expect(page.getByTestId("draft-composer")).toBeVisible();
  await page.getByTestId("Discard").click();
  await expect(page.getByTestId("draft-list")).toBeVisible();
});

