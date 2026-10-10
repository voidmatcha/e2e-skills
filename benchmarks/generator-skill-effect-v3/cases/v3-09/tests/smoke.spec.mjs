import { expect, test } from "@playwright/test";

test("shows the flashcards heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Flashcards" })).toBeVisible();
});
