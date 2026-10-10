import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("shows tip and total for the default percentage", async ({ page }) => {
  await page.getByLabel("Bill amount").fill("100");
  await expect(page.locator("#tc-tip")).toHaveText("Tip: $15.00");
  await expect(page.locator("#tc-total")).toHaveText("Total: $115.00");
  await expect(page.locator("#tc-error")).toHaveText("");
});

test("shows tip and total for a chosen percentage", async ({ page }) => {
  await page.getByLabel("Bill amount").fill("42.50");
  await page.getByLabel("Tip percentage").selectOption("20");
  await expect(page.locator("#tc-tip")).toHaveText("Tip: $8.50");
  await expect(page.locator("#tc-total")).toHaveText("Total: $51.00");
});

test("changing the percentage recomputes tip and total", async ({ page }) => {
  await page.getByLabel("Bill amount").fill("80");
  await page.getByLabel("Tip percentage").selectOption("10");
  await expect(page.locator("#tc-tip")).toHaveText("Tip: $8.00");
  await expect(page.locator("#tc-total")).toHaveText("Total: $88.00");

  await page.getByLabel("Tip percentage").selectOption("20");
  await expect(page.locator("#tc-tip")).toHaveText("Tip: $16.00");
  await expect(page.locator("#tc-total")).toHaveText("Total: $96.00");
});

for (const [name, value] of [
  ["non-numeric", "abc"],
  ["negative", "-5"],
  ["zero", "0"],
]) {
  test(`${name} amount shows an error and clears results`, async ({ page }) => {
    const amount = page.getByLabel("Bill amount");
    await amount.fill("100");
    await expect(page.locator("#tc-tip")).toHaveText("Tip: $15.00");

    await amount.fill(value);
    await expect(page.getByRole("alert")).toHaveText("Enter a positive amount");
    await expect(page.locator("#tc-tip")).toHaveText("");
    await expect(page.locator("#tc-total")).toHaveText("");
  });
}

test("a valid amount after an error clears the error", async ({ page }) => {
  const amount = page.getByLabel("Bill amount");
  await amount.fill("-5");
  await expect(page.getByRole("alert")).toHaveText("Enter a positive amount");
  await amount.fill("20");
  await expect(page.getByRole("alert")).toHaveText("");
  await expect(page.locator("#tc-tip")).toHaveText("Tip: $3.00");
  await expect(page.locator("#tc-total")).toHaveText("Total: $23.00");
});
