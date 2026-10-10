import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

const amount = (page) => page.getByLabel("Bill amount");
const percent = (page) => page.getByLabel("Tip percentage");
const error = (page) => page.getByRole("alert");
const tip = (page) => page.locator("#tc-tip");
const total = (page) => page.locator("#tc-total");

test("shows tip and total for a bill amount at the default percentage", async ({ page }) => {
  await amount(page).fill("50");

  await expect(tip(page)).toHaveText("Tip: $7.50");
  await expect(total(page)).toHaveText("Total: $57.50");
  await expect(error(page)).toBeEmpty();
});

test("recomputes tip and total when the percentage changes", async ({ page }) => {
  await amount(page).fill("80");
  await expect(tip(page)).toHaveText("Tip: $12.00");
  await expect(total(page)).toHaveText("Total: $92.00");

  await percent(page).selectOption("20");
  await expect(tip(page)).toHaveText("Tip: $16.00");
  await expect(total(page)).toHaveText("Total: $96.00");

  await percent(page).selectOption("10");
  await expect(tip(page)).toHaveText("Tip: $8.00");
  await expect(total(page)).toHaveText("Total: $88.00");
});

for (const invalid of ["abc", "-5", "0"]) {
  test(`rejects the amount "${invalid}" and clears tip and total`, async ({ page }) => {
    await amount(page).fill("50");
    await expect(tip(page)).toHaveText("Tip: $7.50");
    await expect(total(page)).toHaveText("Total: $57.50");

    await amount(page).fill(invalid);

    await expect(error(page)).toHaveText("Enter a positive amount");
    await expect(tip(page)).toBeEmpty();
    await expect(total(page)).toBeEmpty();
  });
}
