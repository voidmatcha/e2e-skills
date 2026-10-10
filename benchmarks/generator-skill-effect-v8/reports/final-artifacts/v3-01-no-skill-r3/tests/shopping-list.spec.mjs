import { expect, test } from "@playwright/test";

const itemRows = (page) => page.getByRole("list", { name: "Items" }).locator("li");
const expectItemNames = (page, names) =>
  expect(page.getByRole("list", { name: "Items" }).locator("li .name")).toHaveText(names);

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shows seeded items and appends newly added items with position numbers", async ({ page }) => {
  await page.goto("/");

  await expect(itemRows(page)).toHaveCount(3);
  await expect(page.getByText("3 items · 0 bought")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear bought" })).toBeHidden();
  await expectItemNames(page, ["Oat milk", "Lemons", "Rye bread"]);
  await expect(itemRows(page).nth(0).locator(".pos")).toHaveText("1");
  await expect(itemRows(page).nth(1).locator(".pos")).toHaveText("2");
  await expect(itemRows(page).nth(2).locator(".pos")).toHaveText("3");

  await page.getByLabel("New item").fill("Apples");
  await page.getByRole("button", { name: "Add" }).click();

  await expect(itemRows(page)).toHaveCount(4);
  await expectItemNames(page, ["Oat milk", "Lemons", "Rye bread", "Apples"]);
  await expect(itemRows(page).nth(3).locator(".pos")).toHaveText("4");
  await expect(page.getByText("4 items · 0 bought")).toBeVisible();
});

test("moves items up and down, updates positions, and disables impossible moves", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("button", { name: "Move Oat milk up" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Rye bread down" })).toBeDisabled();

  await page.getByRole("button", { name: "Move Lemons up" }).click();
  await expectItemNames(page, ["Lemons", "Oat milk", "Rye bread"]);
  await expect(itemRows(page).nth(0)).toContainText("1Lemons");
  await expect(itemRows(page).nth(1)).toContainText("2Oat milk");
  await expect(page.getByRole("button", { name: "Move Lemons up" })).toBeDisabled();

  await page.getByRole("button", { name: "Move Lemons down" }).click();
  await expectItemNames(page, ["Oat milk", "Lemons", "Rye bread"]);
  await expect(itemRows(page).nth(0)).toContainText("1Oat milk");
  await expect(itemRows(page).nth(1)).toContainText("2Lemons");
  await expect(page.getByRole("button", { name: "Move Rye bread down" })).toBeDisabled();
});

test("tracks bought items, clears them, and persists order and bought state after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Move Rye bread up" }).click();
  await page.getByLabel("Bought Rye bread").check();

  await expect(page.getByText("3 items · 1 bought")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear bought" })).toBeVisible();
  await expectItemNames(page, ["Oat milk", "Rye bread", "Lemons"]);

  await page.reload();

  await expect(page.getByText("3 items · 1 bought")).toBeVisible();
  await expect(page.getByLabel("Bought Rye bread")).toBeChecked();
  await expectItemNames(page, ["Oat milk", "Rye bread", "Lemons"]);

  await page.getByRole("button", { name: "Clear bought" }).click();

  await expect(page.getByText("2 items · 0 bought")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear bought" })).toBeHidden();
  await expectItemNames(page, ["Oat milk", "Lemons"]);
});
