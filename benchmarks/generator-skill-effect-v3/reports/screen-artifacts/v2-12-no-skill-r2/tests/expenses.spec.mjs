import { expect, test } from "@playwright/test";

const ERROR = "Amount must be a positive number";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

async function addExpense(page, description, amount) {
  await page.getByLabel("Description").fill(description);
  await page.getByLabel("Amount").fill(amount);
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByLabel("Description")).toHaveValue("");
}

test("adds expenses newest first with formatted amounts and total", async ({ page }) => {
  await addExpense(page, "Coffee", "12.5");
  await addExpense(page, "Lunch", "7");

  const items = page.getByRole("list", { name: "Expenses" }).getByRole("listitem");
  await expect(items).toHaveCount(2);
  await expect(items.nth(0)).toContainText("Lunch");
  await expect(items.nth(0)).toContainText("$7.00");
  await expect(items.nth(1)).toContainText("Coffee");
  await expect(items.nth(1)).toContainText("$12.50");
  await expect(page.locator("#ex-total")).toHaveText("Total: $19.50");
});

for (const [name, value] of [
  ["empty", ""],
  ["zero", "0"],
  ["negative", "-5"],
  ["not a number", "abc"],
]) {
  test(`invalid amount (${name}) shows an error on blur and refuses Add`, async ({ page, request }) => {
    const amount = page.getByLabel("Amount");
    await page.getByLabel("Description").fill("Bad");
    await amount.fill(value);
    await amount.blur();
    await expect(page.locator("#ex-amount-error")).toHaveText(ERROR);

    await page.getByRole("button", { name: "Add" }).click();
    await expect(page.locator("#ex-amount-error")).toHaveText(ERROR);
    await expect(page.getByRole("listitem")).toHaveCount(0);
    await expect(page.locator("#ex-total")).toHaveText("Total: $0.00");
    expect(await (await request.get("/api/expenses")).json()).toEqual([]);

    await amount.fill("3");
    await expect(page.locator("#ex-amount-error")).toHaveText("");
    await page.getByRole("button", { name: "Add" }).click();
    await expect(page.getByRole("listitem")).toHaveCount(1);
    await expect(page.locator("#ex-total")).toHaveText("Total: $3.00");
  });
}

test("edits an expense amount in place and the total follows", async ({ page }) => {
  await addExpense(page, "Coffee", "10");
  await addExpense(page, "Lunch", "5");

  await page.getByRole("button", { name: "Edit Coffee" }).click();
  await page.getByLabel("New amount for Coffee").fill("20.25");
  await page.getByRole("button", { name: "Save Coffee" }).click();

  const items = page.getByRole("listitem");
  await expect(items).toHaveCount(2);
  await expect(items.nth(1)).toContainText("Coffee");
  await expect(items.nth(1)).toContainText("$20.25");
  await expect(page.locator("#ex-total")).toHaveText("Total: $25.25");
});

test("deletes an expense and the total follows", async ({ page }) => {
  await addExpense(page, "Coffee", "10");
  await addExpense(page, "Lunch", "5");

  await page.getByRole("button", { name: "Delete Lunch" }).click();

  await expect(page.getByRole("listitem")).toHaveCount(1);
  await expect(page.getByRole("listitem")).toContainText("Coffee");
  await expect(page.locator("#ex-total")).toHaveText("Total: $10.00");
});

test("expenses, edits and deletions survive a reload", async ({ page }) => {
  await addExpense(page, "Coffee", "10");
  await addExpense(page, "Lunch", "5");
  await addExpense(page, "Taxi", "8");

  await page.getByRole("button", { name: "Edit Coffee" }).click();
  await page.getByLabel("New amount for Coffee").fill("11.5");
  await page.getByRole("button", { name: "Save Coffee" }).click();
  await expect(page.locator("#ex-total")).toHaveText("Total: $24.50");
  await page.getByRole("button", { name: "Delete Lunch" }).click();
  await expect(page.locator("#ex-total")).toHaveText("Total: $19.50");

  await page.reload();

  const items = page.getByRole("listitem");
  await expect(items).toHaveCount(2);
  await expect(items.nth(0)).toContainText("Taxi");
  await expect(items.nth(0)).toContainText("$8.00");
  await expect(items.nth(1)).toContainText("Coffee");
  await expect(items.nth(1)).toContainText("$11.50");
  await expect(page.getByText("Lunch")).toHaveCount(0);
  await expect(page.locator("#ex-total")).toHaveText("Total: $19.50");
});
