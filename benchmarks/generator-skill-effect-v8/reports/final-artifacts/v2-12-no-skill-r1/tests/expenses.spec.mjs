import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const descriptionField = (page) => page.getByLabel("Description");
const amountField = (page) => page.getByLabel("Amount");
const expensesList = (page) => page.getByRole("list", { name: "Expenses" });
const expenseRows = (page) => expensesList(page).getByRole("listitem");

async function addExpense(page, description, amount) {
  await descriptionField(page).fill(description);
  await amountField(page).fill(amount);
  await page.getByRole("button", { name: "Add" }).click();
}

test("adds expenses newest first with formatted amounts and updated total", async ({ page }) => {
  await page.goto("/");

  await addExpense(page, "Coffee", "4.5");
  await addExpense(page, "Notebook", "12.50");

  await expect(expenseRows(page)).toHaveText([
    "Notebook $12.50EditDelete",
    "Coffee $4.50EditDelete",
  ]);
  await expect(page.locator("#ex-total")).toHaveText("Total: $17.00");

  await page.reload();

  await expect(expenseRows(page)).toHaveText([
    "Notebook $12.50EditDelete",
    "Coffee $4.50EditDelete",
  ]);
  await expect(page.locator("#ex-total")).toHaveText("Total: $17.00");
});

test("rejects invalid amounts on blur and allows add after the amount is fixed", async ({ page }) => {
  await page.goto("/");

  for (const value of ["", "0", "-1", "not a number"]) {
    await amountField(page).fill(value);
    await descriptionField(page).focus();
    await expect(page.getByText("Amount must be a positive number")).toBeVisible();
  }

  await descriptionField(page).fill("Tea");
  await amountField(page).fill("0");
  await page.getByRole("button", { name: "Add" }).click();

  await expect(page.getByText("Amount must be a positive number")).toBeVisible();
  await expect(expenseRows(page)).toHaveCount(0);
  await expect(page.locator("#ex-total")).toHaveText("Total: $0.00");

  await amountField(page).fill("3");
  await expect(page.getByText("Amount must be a positive number")).toBeHidden();
  await page.getByRole("button", { name: "Add" }).click();

  await expect(expenseRows(page)).toHaveText(["Tea $3.00EditDelete"]);
  await expect(page.locator("#ex-total")).toHaveText("Total: $3.00");
});

test("edits an expense amount in place and keeps the change after reload", async ({ page }) => {
  await page.goto("/");
  await addExpense(page, "Lunch", "8");
  await addExpense(page, "Parking", "6");

  await page.getByRole("button", { name: "Edit Lunch" }).click();
  await page.getByLabel("New amount for Lunch").fill("10.25");
  await page.getByRole("button", { name: "Save Lunch" }).click();

  await expect(expenseRows(page)).toHaveText([
    "Parking $6.00EditDelete",
    "Lunch $10.25EditDelete",
  ]);
  await expect(page.locator("#ex-total")).toHaveText("Total: $16.25");

  await page.reload();

  await expect(expenseRows(page)).toHaveText([
    "Parking $6.00EditDelete",
    "Lunch $10.25EditDelete",
  ]);
  await expect(page.locator("#ex-total")).toHaveText("Total: $16.25");
});

test("deletes an expense and keeps it removed after reload", async ({ page }) => {
  await page.goto("/");
  await addExpense(page, "Train", "2.75");
  await addExpense(page, "Groceries", "20");

  await page.getByRole("button", { name: "Delete Train" }).click();

  await expect(expenseRows(page)).toHaveText(["Groceries $20.00EditDelete"]);
  await expect(page.locator("#ex-total")).toHaveText("Total: $20.00");

  await page.reload();

  await expect(expenseRows(page)).toHaveText(["Groceries $20.00EditDelete"]);
  await expect(page.locator("#ex-total")).toHaveText("Total: $20.00");
});
