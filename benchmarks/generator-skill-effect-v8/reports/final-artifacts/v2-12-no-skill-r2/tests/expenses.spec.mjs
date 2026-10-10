import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const addExpense = async (page, description, amount) => {
  await page.getByLabel("Description").fill(description);
  await page.getByLabel("Amount").fill(amount);
  await page.getByRole("button", { name: "Add" }).click();
};

test("adds expenses newest first and updates the total", async ({ page }) => {
  await page.goto("/");

  await addExpense(page, "Coffee", "4");
  await addExpense(page, "Lunch", "12.5");

  const expenses = page.getByRole("list", { name: "Expenses" }).getByRole("listitem");
  await expect(expenses).toHaveCount(2);
  await expect(expenses.nth(0)).toContainText("Lunch $12.50");
  await expect(expenses.nth(1)).toContainText("Coffee $4.00");
  await expect(page.locator("#ex-total")).toHaveText("Total: $16.50");
});

test("rejects invalid amounts on blur and allows add once fixed", async ({ page }) => {
  await page.goto("/");

  for (const amount of ["", "0", "-1", "abc"]) {
    await page.getByLabel("Amount").fill(amount);
    await page.getByLabel("Description").focus();
    await expect(page.getByText("Amount must be a positive number")).toBeVisible();
  }

  await page.getByLabel("Description").fill("Fixed amount");
  await page.getByLabel("Amount").fill("0");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("Amount must be a positive number")).toBeVisible();
  await expect(page.getByRole("list", { name: "Expenses" }).getByRole("listitem")).toHaveCount(0);

  await page.getByLabel("Amount").fill("8.25");
  await page.getByRole("button", { name: "Add" }).click();

  await expect(page.getByRole("listitem")).toContainText("Fixed amount $8.25");
  await expect(page.locator("#ex-total")).toHaveText("Total: $8.25");
});

test("edits an expense amount in place and persists after reload", async ({ page }) => {
  await page.goto("/");
  await addExpense(page, "Train fare", "3");
  await addExpense(page, "Books", "10");

  await page.getByRole("button", { name: "Edit Train fare" }).click();
  await page.getByLabel("New amount for Train fare").fill("5.5");
  await page.getByRole("button", { name: "Save Train fare" }).click();

  await expect(page.getByRole("listitem").filter({ hasText: "Train fare" })).toContainText("$5.50");
  await expect(page.locator("#ex-total")).toHaveText("Total: $15.50");

  await page.reload();

  await expect(page.getByRole("listitem").filter({ hasText: "Books" })).toContainText("$10.00");
  await expect(page.getByRole("listitem").filter({ hasText: "Train fare" })).toContainText("$5.50");
  await expect(page.locator("#ex-total")).toHaveText("Total: $15.50");
});

test("deletes an expense and persists the removal after reload", async ({ page }) => {
  await page.goto("/");
  await addExpense(page, "Notebook", "6");
  await addExpense(page, "Dinner", "21");

  await page.getByRole("button", { name: "Delete Notebook" }).click();

  await expect(page.getByText("Notebook")).toHaveCount(0);
  await expect(page.getByRole("listitem")).toContainText("Dinner $21.00");
  await expect(page.locator("#ex-total")).toHaveText("Total: $21.00");

  await page.reload();

  await expect(page.getByText("Notebook")).toHaveCount(0);
  await expect(page.getByRole("listitem")).toContainText("Dinner $21.00");
  await expect(page.locator("#ex-total")).toHaveText("Total: $21.00");
});
