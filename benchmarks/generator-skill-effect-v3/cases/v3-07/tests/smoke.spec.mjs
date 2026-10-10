import { expect, test } from "@playwright/test";

test("shows the seat picker heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Pick your seats" })).toBeVisible();
});
