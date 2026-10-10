import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("list", { name: "Items", exact: true }).getByRole("listitem")).toHaveCount(3);
});

const itemsList = (page) => page.getByRole("list", { name: "Items", exact: true });

const itemRows = (page) => itemsList(page).getByRole("listitem");

const itemRow = (page, name) => itemRows(page).filter({ hasText: name });

const expectItems = async (page, expected) => {
  await expect(itemRows(page)).toHaveText(
    expected.map((name, index) => new RegExp(`^\\s*${index + 1}\\s*${name}\\s*Move up\\s*Move down\\s*$`)),
  );
};

test("shows the seeded shopping list with boundary move controls", async ({ page }) => {
  await expectItems(page, ["Oat milk", "Lemons", "Rye bread"]);

  await expect(itemRow(page, "Oat milk").getByRole("button", { name: "Move Oat milk up", exact: true })).toBeDisabled();
  await expect(itemRow(page, "Rye bread").getByRole("button", { name: "Move Rye bread down", exact: true })).toBeDisabled();
  await expect(page.getByText("3 items · 0 bought")).toBeVisible();
});

test("adds an item at the end and keeps it after reload", async ({ page }) => {
  const createItem = page.waitForResponse(
    (response) => response.url().endsWith("/api/items") && response.request().method() === "POST",
  );

  await page.getByRole("textbox", { name: "New item", exact: true }).fill("Apples");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await createItem;

  await expectItems(page, ["Oat milk", "Lemons", "Rye bread", "Apples"]);
  await expect(page.getByText("4 items · 0 bought")).toBeVisible();

  await page.reload();
  await expectItems(page, ["Oat milk", "Lemons", "Rye bread", "Apples"]);
});

test("moves items up and down with position numbers following after reload", async ({ page }) => {
  const moveDown = page.waitForResponse(
    (response) => response.url().endsWith("/api/order") && response.request().method() === "PUT",
  );
  await itemRow(page, "Lemons").getByRole("button", { name: "Move Lemons down", exact: true }).click();
  await moveDown;
  await expectItems(page, ["Oat milk", "Rye bread", "Lemons"]);

  const moveUp = page.waitForResponse(
    (response) => response.url().endsWith("/api/order") && response.request().method() === "PUT",
  );
  await itemRow(page, "Rye bread").getByRole("button", { name: "Move Rye bread up", exact: true }).click();
  await moveUp;

  await expectItems(page, ["Rye bread", "Oat milk", "Lemons"]);
  await expect(itemRow(page, "Rye bread").getByRole("button", { name: "Move Rye bread up", exact: true })).toBeDisabled();
  await expect(itemRow(page, "Lemons").getByRole("button", { name: "Move Lemons down", exact: true })).toBeDisabled();

  await page.reload();
  await expectItems(page, ["Rye bread", "Oat milk", "Lemons"]);
});

test("tracks bought items and clears them from the stored list", async ({ page }) => {
  const markBought = page.waitForResponse(
    (response) => response.url().includes("/api/items/") && response.request().method() === "PATCH",
  );
  await itemRow(page, "Lemons").getByRole("checkbox", { name: "Bought Lemons", exact: true }).check();
  await markBought;

  await expect(page.getByText("3 items · 1 bought")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear bought", exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByText("3 items · 1 bought")).toBeVisible();
  await expect(itemRow(page, "Lemons").getByRole("checkbox", { name: "Bought Lemons", exact: true })).toBeChecked();

  const clearBought = page.waitForResponse(
    (response) => response.url().endsWith("/api/items/clear-bought") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Clear bought", exact: true }).click();
  await clearBought;

  await expectItems(page, ["Oat milk", "Rye bread"]);
  await expect(page.getByText("2 items · 0 bought")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear bought", exact: true })).toHaveCount(0);

  await page.reload();
  await expectItems(page, ["Oat milk", "Rye bread"]);
  await expect(page.getByText("2 items · 0 bought")).toBeVisible();
});
