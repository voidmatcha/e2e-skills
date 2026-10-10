import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByRole("listitem")).toHaveCount(3);
});

const rows = (page) => page.getByRole("list", { name: "Items" }).getByRole("listitem");
const expectOrder = async (page, names) => {
  await expect(rows(page)).toHaveCount(names.length);
  for (const [i, name] of names.entries()) {
    await expect(rows(page).nth(i).locator(".pos")).toHaveText(String(i + 1));
    await expect(rows(page).nth(i).locator(".name")).toHaveText(name);
  }
};

test("shows the seeded items in order", async ({ page }) => {
  await expectOrder(page, ["Oat milk", "Lemons", "Rye bread"]);
  await expect(page.locator("#sl-status")).toHaveText("3 items · 0 bought");
});

test("adding an item appends it with its position number", async ({ page }) => {
  await page.getByRole("textbox", { name: "New item" }).fill("Butter");
  await page.getByRole("button", { name: "Add" }).click();
  await expectOrder(page, ["Oat milk", "Lemons", "Rye bread", "Butter"]);
  await expect(page.getByRole("textbox", { name: "New item" })).toHaveValue("");
  await expect(page.locator("#sl-status")).toHaveText("4 items · 0 bought");
});

test("Move up and Move down swap neighbours and numbers follow", async ({ page }) => {
  await page.getByRole("button", { name: "Move Lemons up" }).click();
  await expectOrder(page, ["Lemons", "Oat milk", "Rye bread"]);
  await page.getByRole("button", { name: "Move Lemons down" }).click();
  await expectOrder(page, ["Oat milk", "Lemons", "Rye bread"]);
  await page.getByRole("button", { name: "Move Oat milk down" }).click();
  await expectOrder(page, ["Lemons", "Oat milk", "Rye bread"]);
});

test("first Move up and last Move down are disabled", async ({ page }) => {
  await expect(page.getByRole("button", { name: "Move Oat milk up" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Oat milk down" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Move Rye bread down" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Rye bread up" })).toBeEnabled();

  await page.getByRole("button", { name: "Move Rye bread up" }).click();
  await expectOrder(page, ["Oat milk", "Rye bread", "Lemons"]);
  await expect(page.getByRole("button", { name: "Move Lemons down" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Rye bread down" })).toBeEnabled();
});

test("ticking Bought updates the status line and shows Clear bought", async ({ page }) => {
  const clear = page.getByRole("button", { name: "Clear bought" });
  await expect(clear).toBeHidden();
  await page.getByRole("checkbox", { name: "Bought Lemons" }).check();
  await expect(page.locator("#sl-status")).toHaveText("3 items · 1 bought");
  await expect(clear).toBeVisible();
  await page.getByRole("checkbox", { name: "Bought Lemons" }).uncheck();
  await expect(page.locator("#sl-status")).toHaveText("3 items · 0 bought");
  await expect(clear).toBeHidden();
});

test("Clear bought removes every bought item", async ({ page }) => {
  await page.getByRole("checkbox", { name: "Bought Oat milk" }).check();
  await page.getByRole("checkbox", { name: "Bought Rye bread" }).check();
  await expect(page.locator("#sl-status")).toHaveText("3 items · 2 bought");
  await page.getByRole("button", { name: "Clear bought" }).click();
  await expectOrder(page, ["Lemons"]);
  await expect(page.locator("#sl-status")).toHaveText("1 item · 0 bought");
  await expect(page.getByRole("button", { name: "Clear bought" })).toBeHidden();
});

test("order and bought state survive a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Move Rye bread up" }).click();
  await expectOrder(page, ["Oat milk", "Rye bread", "Lemons"]);
  await page.getByRole("checkbox", { name: "Bought Rye bread" }).check();
  await expect(page.locator("#sl-status")).toHaveText("3 items · 1 bought");

  await page.reload();
  await expectOrder(page, ["Oat milk", "Rye bread", "Lemons"]);
  await expect(page.getByRole("checkbox", { name: "Bought Rye bread" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Bought Lemons" })).not.toBeChecked();
  await expect(page.locator("#sl-status")).toHaveText("3 items · 1 bought");
  await expect(page.getByRole("button", { name: "Clear bought" })).toBeVisible();
});
