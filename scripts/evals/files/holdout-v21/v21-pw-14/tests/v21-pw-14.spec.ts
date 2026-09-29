import { test, expect } from '@playwright/test';

test("shows book title and author", async ({ page }) => {
  await page.goto("/library");
  await expect(page.getByTestId("book-title")).toHaveText("Dune");
});

