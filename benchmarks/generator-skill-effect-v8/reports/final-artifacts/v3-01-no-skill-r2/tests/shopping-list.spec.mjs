import { expect, test } from "@playwright/test";

const list = (page) => page.getByRole("list", { name: "Items" });
const rows = (page) => list(page).locator("li");
const names = (page) => rows(page).locator(".name");
const positions = (page) => rows(page).locator(".pos");

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("shows the seeded list and appends new items with position numbers", async ({ page }) => {
  await expect(page.getByText("3 items · 0 bought")).toBeVisible();
  await expect(names(page)).toHaveText(["Oat milk", "Lemons", "Rye bread"]);
  await expect(positions(page)).toHaveText(["1", "2", "3"]);

  await expect(rows(page).nth(0).getByRole("button", { name: "Move Oat milk up" })).toBeDisabled();
  await expect(rows(page).nth(2).getByRole("button", { name: "Move Rye bread down" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Clear bought" })).toHaveCount(0);

  await page.getByLabel("New item").fill("Apples");
  await page.getByRole("button", { name: "Add" }).click();

  await expect(page.getByText("4 items · 0 bought")).toBeVisible();
  await expect(names(page)).toHaveText(["Oat milk", "Lemons", "Rye bread", "Apples"]);
  await expect(positions(page)).toHaveText(["1", "2", "3", "4"]);
  await expect(rows(page).nth(3).getByRole("button", { name: "Move Apples down" })).toBeDisabled();
});

test("moves items up and down while keeping position numbers in order", async ({ page }) => {
  await rows(page).nth(1).getByRole("button", { name: "Move Lemons up" }).click();

  await expect(names(page)).toHaveText(["Lemons", "Oat milk", "Rye bread"]);
  await expect(positions(page)).toHaveText(["1", "2", "3"]);
  await expect(rows(page).nth(0).getByRole("button", { name: "Move Lemons up" })).toBeDisabled();

  await rows(page).nth(0).getByRole("button", { name: "Move Lemons down" }).click();

  await expect(names(page)).toHaveText(["Oat milk", "Lemons", "Rye bread"]);
  await expect(positions(page)).toHaveText(["1", "2", "3"]);
  await expect(rows(page).nth(2).getByRole("button", { name: "Move Rye bread down" })).toBeDisabled();
});

test("persists order and bought state, then clears bought items", async ({ page }) => {
  await rows(page).nth(1).getByRole("button", { name: "Move Lemons up" }).click();
  await page.getByLabel("Bought Oat milk").check();

  await expect(page.getByText("3 items · 1 bought")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear bought" })).toBeVisible();

  await page.reload();

  await expect(names(page)).toHaveText(["Lemons", "Oat milk", "Rye bread"]);
  await expect(positions(page)).toHaveText(["1", "2", "3"]);
  await expect(page.getByLabel("Bought Oat milk")).toBeChecked();
  await expect(page.getByText("3 items · 1 bought")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear bought" })).toBeVisible();

  await page.getByRole("button", { name: "Clear bought" }).click();

  await expect(names(page)).toHaveText(["Lemons", "Rye bread"]);
  await expect(positions(page)).toHaveText(["1", "2"]);
  await expect(page.getByText("2 items · 0 bought")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear bought" })).toHaveCount(0);
});
