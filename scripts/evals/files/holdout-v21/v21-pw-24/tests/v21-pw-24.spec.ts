import { test, expect } from '@playwright/test';

test("restores notes and dismisses editor", async ({ page }) => {
  await page.goto("/notes");
  await expect(page.getByTestId("note-editor")).toBeVisible();
  await page.getByTestId("Discard").click();
  await expect(page.getByTestId("note-list")).toBeVisible();
  await expect(page.getByTestId("note-editor")).toBeHidden();
});

