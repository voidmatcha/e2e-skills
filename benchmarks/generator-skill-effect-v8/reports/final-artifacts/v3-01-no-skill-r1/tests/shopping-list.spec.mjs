import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const itemNames = async (page) =>
  page.getByRole("listitem").locator(".name").allTextContents();

const itemPositions = async (page) =>
  page.getByRole("listitem").locator(".pos").allTextContents();

test("shows the seeded shopping list with boundary move buttons disabled", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("list", { name: "Items" })).toBeVisible();
  await expect(page.getByRole("listitem")).toHaveCount(3);
  await expect(page.getByText("3 items · 0 bought")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear bought" })).toBeHidden();
  await expect(page.getByRole("button", { name: "Move Oat milk up" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Rye bread down" })).toBeDisabled();

  await expect.poll(() => itemNames(page)).toEqual(["Oat milk", "Lemons", "Rye bread"]);
  await expect.poll(() => itemPositions(page)).toEqual(["1", "2", "3"]);
});

test("adds an item at the end with the next position number", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("New item").fill("Coffee");
  await page.getByRole("button", { name: "Add" }).click();

  await expect(page.getByRole("listitem")).toHaveCount(4);
  await expect(page.getByText("4 items · 0 bought")).toBeVisible();
  await expect.poll(() => itemNames(page)).toEqual(["Oat milk", "Lemons", "Rye bread", "Coffee"]);
  await expect.poll(() => itemPositions(page)).toEqual(["1", "2", "3", "4"]);
  await expect(page.getByRole("button", { name: "Move Coffee down" })).toBeDisabled();
});

test("moves items up and down while position numbers follow the order", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Move Lemons up" }).click();
  await expect.poll(() => itemNames(page)).toEqual(["Lemons", "Oat milk", "Rye bread"]);
  await expect.poll(() => itemPositions(page)).toEqual(["1", "2", "3"]);
  await expect(page.getByRole("button", { name: "Move Lemons up" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Rye bread down" })).toBeDisabled();

  await page.getByRole("button", { name: "Move Lemons down" }).click();
  await expect.poll(() => itemNames(page)).toEqual(["Oat milk", "Lemons", "Rye bread"]);
  await expect.poll(() => itemPositions(page)).toEqual(["1", "2", "3"]);
  await expect(page.getByRole("button", { name: "Move Oat milk up" })).toBeDisabled();
});

test("tracks bought items and clears them", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("button", { name: "Clear bought" })).toBeHidden();

  await page.getByLabel("Bought Lemons").check();
  await expect(page.getByText("3 items · 1 bought")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear bought" })).toBeVisible();

  await page.getByRole("button", { name: "Clear bought" }).click();
  await expect(page.getByText("2 items · 0 bought")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear bought" })).toBeHidden();
  await expect.poll(() => itemNames(page)).toEqual(["Oat milk", "Rye bread"]);
  await expect.poll(() => itemPositions(page)).toEqual(["1", "2"]);
});

test("persists order and bought state after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Move Rye bread up" }).click();
  await page.getByLabel("Bought Rye bread").check();
  await expect.poll(() => itemNames(page)).toEqual(["Oat milk", "Rye bread", "Lemons"]);
  await expect(page.getByText("3 items · 1 bought")).toBeVisible();

  await page.reload();

  await expect.poll(() => itemNames(page)).toEqual(["Oat milk", "Rye bread", "Lemons"]);
  await expect.poll(() => itemPositions(page)).toEqual(["1", "2", "3"]);
  await expect(page.getByLabel("Bought Rye bread")).toBeChecked();
  await expect(page.getByText("3 items · 1 bought")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear bought" })).toBeVisible();
});
