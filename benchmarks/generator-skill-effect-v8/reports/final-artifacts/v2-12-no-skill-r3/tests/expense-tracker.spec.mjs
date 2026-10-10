import { expect, test } from "@playwright/test";

const resetExpenses = async (request) => {
  await request.post("/api/reset");
};

const addExpense = async (page, description, amount) => {
  await page.getByLabel("Description").fill(description);
  await page.getByLabel("Amount").fill(String(amount));
  await page.getByRole("button", { name: "Add" }).click();
};

const expenses = (page) =>
  page.getByRole("list", { name: "Expenses" }).getByRole("listitem");

test.beforeEach(async ({ page, request }) => {
  await resetExpenses(request);
  await page.goto("/");
});

test("adds expenses newest first and keeps them after reload", async ({ page }) => {
  await addExpense(page, "Lunch", "12.5");
  await addExpense(page, "Coffee", "3");

  await expect(expenses(page)).toHaveCount(2);
  await expect(expenses(page).nth(0)).toContainText("Coffee");
  await expect(expenses(page).nth(0)).toContainText("$3.00");
  await expect(expenses(page).nth(1)).toContainText("Lunch");
  await expect(expenses(page).nth(1)).toContainText("$12.50");
  await expect(page.getByText("Total: $15.50")).toBeVisible();

  await page.reload();

  await expect(expenses(page)).toHaveCount(2);
  await expect(expenses(page).nth(0)).toContainText("Coffee");
  await expect(expenses(page).nth(0)).toContainText("$3.00");
  await expect(expenses(page).nth(1)).toContainText("Lunch");
  await expect(expenses(page).nth(1)).toContainText("$12.50");
  await expect(page.getByText("Total: $15.50")).toBeVisible();
});

test("rejects invalid amounts until the amount is fixed", async ({ page }) => {
  const amount = page.getByLabel("Amount");
  const description = page.getByLabel("Description");
  const error = page.getByRole("alert");

  await description.fill("Bad amount");

  for (const invalidAmount of ["", "0", "-1", "not a number"]) {
    await amount.fill(invalidAmount);
    await description.focus();
    await expect(error).toHaveText("Amount must be a positive number");

    await page.getByRole("button", { name: "Add" }).click();
    await expect(error).toHaveText("Amount must be a positive number");
    await expect(expenses(page)).toHaveCount(0);
  }

  await amount.fill("8.75");
  await expect(error).toHaveText("");
  await page.getByRole("button", { name: "Add" }).click();

  await expect(expenses(page)).toHaveCount(1);
  await expect(expenses(page).first()).toContainText("Bad amount");
  await expect(expenses(page).first()).toContainText("$8.75");
  await expect(page.getByText("Total: $8.75")).toBeVisible();
});

test("edits an expense amount and persists the updated total", async ({ page }) => {
  await addExpense(page, "Train ticket", "9");
  await addExpense(page, "Notebook", "4.25");

  await page.getByRole("button", { name: "Edit Train ticket" }).click();
  await page.getByLabel("New amount for Train ticket").fill("11.5");
  await page.getByRole("button", { name: "Save Train ticket" }).click();

  await expect(expenses(page).filter({ hasText: "Train ticket" })).toContainText("$11.50");
  await expect(page.getByText("Total: $15.75")).toBeVisible();

  await page.reload();

  await expect(expenses(page).filter({ hasText: "Train ticket" })).toContainText("$11.50");
  await expect(page.getByText("Total: $15.75")).toBeVisible();
});

test("deletes an expense and keeps it deleted after reload", async ({ page }) => {
  await addExpense(page, "Taxi", "18");
  await addExpense(page, "Snack", "2.5");

  await page.getByRole("button", { name: "Delete Taxi" }).click();

  await expect(expenses(page)).toHaveCount(1);
  await expect(expenses(page).first()).toContainText("Snack");
  await expect(expenses(page).first()).toContainText("$2.50");
  await expect(page.getByText("Total: $2.50")).toBeVisible();

  await page.reload();

  await expect(expenses(page)).toHaveCount(1);
  await expect(expenses(page).first()).toContainText("Snack");
  await expect(page.getByText("Total: $2.50")).toBeVisible();
});
