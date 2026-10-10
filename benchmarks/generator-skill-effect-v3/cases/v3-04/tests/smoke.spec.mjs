import { expect, test } from "@playwright/test";

test("shows the playlist heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Playlist" })).toBeVisible();
});
