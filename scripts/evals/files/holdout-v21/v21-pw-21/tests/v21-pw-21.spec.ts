import { test, expect } from '@playwright/test';

test("shows Geometry and 45 min on the courses page", async ({ page }) => {
  await page.goto("/courses");
  await expect(page.getByTestId("course-title")).toHaveText("Geometry");
});

test("restores courses list and closes panel", async ({ page }) => {
  await page.goto("/courses?panel=open");
  await expect(page.getByTestId("lesson-panel")).toBeVisible();
  await page.getByTestId("Close lesson").click();
  await expect(page.getByTestId("course-list")).toBeVisible();
});

