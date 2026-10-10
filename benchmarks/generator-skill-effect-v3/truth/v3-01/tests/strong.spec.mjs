import { expect, test } from "@playwright/test";

const items = (page) => page.getByRole("list", { name: "Items" }).getByRole("listitem");
const status = (page) => page.getByText(/^\d+ items? · \d+ bought$/);

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(items(page)).toHaveCount(3);
});

test("adding appends with the next position number", async ({ page }) => {
  await page.getByRole("textbox", { name: "New item" }).fill("Coffee");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(items(page)).toHaveCount(4);
  await expect(items(page).nth(3)).toContainText("Coffee");
  await expect(items(page).nth(3)).toContainText("4");
  await expect(status(page)).toHaveText("4 items · 0 bought");
});

test("moving swaps neighbours and renumbers; edge buttons are disabled", async ({ page }) => {
  await expect(page.getByRole("button", { name: "Move Oat milk up" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Rye bread down" })).toBeDisabled();
  await page.getByRole("button", { name: "Move Lemons up" }).click();
  await expect(items(page)).toHaveText([/^1.*Lemons/, /^2.*Oat milk/, /^3.*Rye bread/]);
  await expect(page.getByRole("button", { name: "Move Lemons up" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Oat milk up" })).toBeEnabled();
  await page.reload();
  await expect(items(page)).toHaveText([/^1.*Lemons/, /^2.*Oat milk/, /^3.*Rye bread/]);
});

test("bought updates the status line and reveals clear bought", async ({ page }) => {
  await expect(page.getByRole("button", { name: "Clear bought" })).toBeHidden();
  await page.getByRole("checkbox", { name: "Bought Lemons" }).check();
  await expect(status(page)).toHaveText("3 items · 1 bought");
  await expect(page.getByRole("button", { name: "Clear bought" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("checkbox", { name: "Bought Lemons" })).toBeChecked();
  await expect(status(page)).toHaveText("3 items · 1 bought");
  await page.getByRole("button", { name: "Clear bought" }).click();
  await expect(items(page)).toHaveText([/Oat milk/, /Rye bread/]);
  await expect(status(page)).toHaveText("2 items · 0 bought");
  await expect(page.getByRole("button", { name: "Clear bought" })).toBeHidden();
});
