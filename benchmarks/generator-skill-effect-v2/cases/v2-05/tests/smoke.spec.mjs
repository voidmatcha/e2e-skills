import { expect, test } from "@playwright/test";

test("shows the appointments heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Appointments" })).toBeVisible();
});
