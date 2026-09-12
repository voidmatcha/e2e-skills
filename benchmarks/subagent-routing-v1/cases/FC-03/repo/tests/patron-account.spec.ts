import { expect, test } from "@playwright/test";
import { seedSamplePatron } from "./support/patron-seed";

test.beforeAll(async ({ request }) => {
  await seedSamplePatron(request);
});

test("shows the patron profile", async ({ page }) => {
  await page.goto("/patrons/SAMPLE-PATRON-404");
  await expect(page.getByRole("heading", { name: "Patron account" })).toBeVisible();
});

test("shows active holds", async ({ page }) => {
  await page.goto("/patrons/SAMPLE-PATRON-404/holds");
  await expect(page.getByTestId("active-hold-count")).toHaveText("2");
});

test("shows the fine balance", async ({ page }) => {
  await page.goto("/patrons/SAMPLE-PATRON-404/fines");
  await expect(page.getByTestId("fine-balance")).toHaveText("$0.00");
});
