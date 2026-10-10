import { expect, test } from "@playwright/test";

const rows = (page) => page.getByRole("list", { name: "Items" }).getByRole("listitem");
const status = (page) => page.locator("#sl-status");
const clearButton = (page) => page.getByRole("button", { name: "Clear bought" });

// Each row reads "<position><name>Move upMove down" in order.
async function expectOrder(page, names) {
  await expect(rows(page)).toHaveCount(names.length);
  for (const [i, name] of names.entries()) {
    const row = rows(page).nth(i);
    await expect(row.locator(".pos")).toHaveText(String(i + 1));
    await expect(row.locator(".name")).toHaveText(name);
  }
}

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expectOrder(page, ["Oat milk", "Lemons", "Rye bread"]);
});

test("shows the seeded items with positions", async ({ page }) => {
  await expect(status(page)).toHaveText("3 items · 0 bought");
});

test("adding an item appends it with its position number", async ({ page }) => {
  await page.getByLabel("New item").fill("Coffee");
  await page.getByRole("button", { name: "Add" }).click();
  await expectOrder(page, ["Oat milk", "Lemons", "Rye bread", "Coffee"]);
  await expect(status(page)).toHaveText("4 items · 0 bought");
  await expect(page.getByLabel("New item")).toHaveValue("");
});

test("adding a blank item does nothing", async ({ page }) => {
  await page.getByLabel("New item").fill("   ");
  await page.getByRole("button", { name: "Add" }).click();
  await expectOrder(page, ["Oat milk", "Lemons", "Rye bread"]);
});

test("Move up and Move down swap an item with its neighbour", async ({ page }) => {
  await page.getByRole("button", { name: "Move Lemons up" }).click();
  await expectOrder(page, ["Lemons", "Oat milk", "Rye bread"]);

  await page.getByRole("button", { name: "Move Lemons down" }).click();
  await expectOrder(page, ["Oat milk", "Lemons", "Rye bread"]);

  await page.getByRole("button", { name: "Move Oat milk down" }).click();
  await expectOrder(page, ["Lemons", "Oat milk", "Rye bread"]);
});

test("first Move up and last Move down are disabled", async ({ page }) => {
  await expect(page.getByRole("button", { name: "Move Oat milk up" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Rye bread down" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Oat milk down" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Move Lemons up" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Move Lemons down" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Move Rye bread up" })).toBeEnabled();

  await page.getByRole("button", { name: "Move Rye bread up" }).click();
  await expectOrder(page, ["Oat milk", "Rye bread", "Lemons"]);
  await expect(page.getByRole("button", { name: "Move Lemons down" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Rye bread down" })).toBeEnabled();
});

test("added item gets a disabled Move down as the last item", async ({ page }) => {
  await page.getByLabel("New item").fill("Coffee");
  await page.getByRole("button", { name: "Add" }).click();
  await expectOrder(page, ["Oat milk", "Lemons", "Rye bread", "Coffee"]);
  await expect(page.getByRole("button", { name: "Move Coffee down" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Rye bread down" })).toBeEnabled();
});

test("ticking Bought updates the status line and shows Clear bought", async ({ page }) => {
  await expect(clearButton(page)).toBeHidden();

  await page.getByRole("checkbox", { name: "Bought Lemons" }).check();
  await expect(status(page)).toHaveText("3 items · 1 bought");
  await expect(clearButton(page)).toBeVisible();

  await page.getByRole("checkbox", { name: "Bought Lemons" }).uncheck();
  await expect(status(page)).toHaveText("3 items · 0 bought");
  await expect(clearButton(page)).toBeHidden();
});

test("Clear bought removes every bought item", async ({ page }) => {
  await page.getByRole("checkbox", { name: "Bought Oat milk" }).check();
  await page.getByRole("checkbox", { name: "Bought Rye bread" }).check();
  await expect(status(page)).toHaveText("3 items · 2 bought");

  await clearButton(page).click();
  await expectOrder(page, ["Lemons"]);
  await expect(status(page)).toHaveText("1 item · 0 bought");
  await expect(clearButton(page)).toBeHidden();
});

test("order and bought state survive a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Move Rye bread up" }).click();
  await expectOrder(page, ["Oat milk", "Rye bread", "Lemons"]);
  await page.getByRole("checkbox", { name: "Bought Rye bread" }).check();
  await expect(status(page)).toHaveText("3 items · 1 bought");

  await page.reload();
  await expectOrder(page, ["Oat milk", "Rye bread", "Lemons"]);
  await expect(page.getByRole("checkbox", { name: "Bought Rye bread" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Bought Oat milk" })).not.toBeChecked();
  await expect(status(page)).toHaveText("3 items · 1 bought");
  await expect(clearButton(page)).toBeVisible();
});

test("added and cleared items persist across a reload", async ({ page }) => {
  await page.getByLabel("New item").fill("Coffee");
  await page.getByRole("button", { name: "Add" }).click();
  await expectOrder(page, ["Oat milk", "Lemons", "Rye bread", "Coffee"]);
  await page.getByRole("checkbox", { name: "Bought Oat milk" }).check();
  await clearButton(page).click();
  await expectOrder(page, ["Lemons", "Rye bread", "Coffee"]);

  await page.reload();
  await expectOrder(page, ["Lemons", "Rye bread", "Coffee"]);
  await expect(status(page)).toHaveText("3 items · 0 bought");
});
