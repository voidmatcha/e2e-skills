import { test } from "@playwright/test";

test("places The Glass Harbor on the patron hold list", async ({ page }) => {
  await page.goto("/catalog/the-glass-harbor");
  await page.getByLabel("Library card number").fill("CARD-1042");
  await page.getByRole("button", { name: "Place hold", exact: true }).click();
  await page.getByTestId("hold-confirmation").isVisible();
});
