import { test, expect } from '@playwright/test';

test("shows event title and date", async ({ page }) => {
  await page.goto("/events");
  await expect(page.getByTestId("event-title")).toHaveText("Design Summit");
});

