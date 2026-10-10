import { expect, test } from "@playwright/test";

const names = (page) => page.locator("#sl-list .name");
const positions = (page) => page.locator("#sl-list .pos");
const status = (page) => page.locator("#sl-status");
const clear = (page) => page.getByRole("button", { name: "Clear bought" });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(names(page)).toHaveCount(3);
});

test("shows the seeded items in order", async ({ page }) => {
  await expect(names(page)).toHaveText(["Oat milk", "Lemons", "Rye bread"]);
  await expect(positions(page)).toHaveText(["1", "2", "3"]);
  await expect(status(page)).toHaveText("3 items · 0 bought");
  await expect(clear(page)).toBeHidden();
});

test("adds an item at the end with its position", async ({ page }) => {
  await page.getByLabel("New item").fill("Basil");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(names(page)).toHaveText(["Oat milk", "Lemons", "Rye bread", "Basil"]);
  await expect(positions(page).last()).toHaveText("4");
  await expect(status(page)).toHaveText("4 items · 0 bought");
  await expect(page.getByLabel("New item")).toHaveValue("");
});

test("move up and down swap neighbours and renumber", async ({ page }) => {
  await page.getByRole("button", { name: "Move Lemons up" }).click();
  await expect(names(page)).toHaveText(["Lemons", "Oat milk", "Rye bread"]);
  await expect(positions(page)).toHaveText(["1", "2", "3"]);
  await page.getByRole("button", { name: "Move Lemons down" }).click();
  await expect(names(page)).toHaveText(["Oat milk", "Lemons", "Rye bread"]);
  await page.getByRole("button", { name: "Move Oat milk down" }).click();
  await expect(names(page)).toHaveText(["Lemons", "Oat milk", "Rye bread"]);
});

test("first Move up and last Move down are disabled", async ({ page }) => {
  await expect(page.getByRole("button", { name: "Move Oat milk up" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Rye bread down" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Oat milk down" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Move Rye bread up" })).toBeEnabled();
  await page.getByRole("button", { name: "Move Rye bread up" }).click();
  await expect(page.getByRole("button", { name: "Move Lemons down" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Rye bread down" })).toBeEnabled();
});

test("bought updates the status line and Clear bought removes bought items", async ({ page }) => {
  await expect(clear(page)).toBeHidden();
  await page.getByLabel("Bought Lemons").check();
  await expect(status(page)).toHaveText("3 items · 1 bought");
  await expect(clear(page)).toBeVisible();
  await page.getByLabel("Bought Rye bread").check();
  await expect(status(page)).toHaveText("3 items · 2 bought");
  await clear(page).click();
  await expect(names(page)).toHaveText(["Oat milk"]);
  await expect(positions(page)).toHaveText(["1"]);
  await expect(status(page)).toHaveText("1 item · 0 bought");
  await expect(clear(page)).toBeHidden();
});

test("unticking the last bought item hides Clear bought", async ({ page }) => {
  await page.getByLabel("Bought Lemons").check();
  await expect(clear(page)).toBeVisible();
  await page.getByLabel("Bought Lemons").uncheck();
  await expect(status(page)).toHaveText("3 items · 0 bought");
  await expect(clear(page)).toBeHidden();
});

test("order, bought state and added items survive a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Move Rye bread up" }).click();
  await expect(names(page)).toHaveText(["Oat milk", "Rye bread", "Lemons"]);
  await page.getByLabel("Bought Oat milk").check();
  await expect(status(page)).toHaveText("3 items · 1 bought");
  await page.getByLabel("New item").fill("Basil");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(names(page)).toHaveCount(4);

  await page.reload();
  await expect(names(page)).toHaveText(["Oat milk", "Rye bread", "Lemons", "Basil"]);
  await expect(page.getByLabel("Bought Oat milk")).toBeChecked();
  await expect(page.getByLabel("Bought Lemons")).not.toBeChecked();
  await expect(status(page)).toHaveText("4 items · 1 bought");
  await expect(clear(page)).toBeVisible();
});

test("clearing bought items persists across a reload", async ({ page }) => {
  await page.getByLabel("Bought Oat milk").check();
  await expect(clear(page)).toBeVisible();
  await clear(page).click();
  await expect(names(page)).toHaveText(["Lemons", "Rye bread"]);
  await page.reload();
  await expect(names(page)).toHaveText(["Lemons", "Rye bread"]);
  await expect(status(page)).toHaveText("2 items · 0 bought");
});
