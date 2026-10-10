import { expect, test } from "@playwright/test";

const resetExpenses = async (page) => {
  await page.request.post("/api/reset");
};

const addExpense = async (page, description, amount) => {
  await page.getByLabel("Description").fill(description);
  await page.getByLabel("Amount").fill(amount);

  const request = page.waitForRequest((req) => req.method() === "POST" && req.url().endsWith("/api/expenses"));
  await page.getByRole("button", { name: "Add" }).click();
  await request;
};

test.beforeEach(async ({ page }) => {
  await resetExpenses(page);
  await page.goto("/");
});

test("adds expenses newest first, formats amounts, updates the total, and survives reload", async ({ page }) => {
  await addExpense(page, "Coffee", "3");
  await addExpense(page, "Lunch", "12.5");

  const expenses = page.getByRole("list", { name: "Expenses" }).getByRole("listitem");

  await expect(expenses).toHaveText(["Lunch $12.50EditDelete", "Coffee $3.00EditDelete"]);
  await expect(page.getByText("Total: $15.50")).toBeVisible();

  await page.reload();
  await expect(expenses).toHaveText(["Lunch $12.50EditDelete", "Coffee $3.00EditDelete"]);
  await expect(page.getByText("Total: $15.50")).toBeVisible();
});

test("refuses invalid amounts until the amount is fixed", async ({ page }) => {
  const amount = page.getByLabel("Amount");
  const add = page.getByRole("button", { name: "Add" });
  const error = page.getByText("Amount must be a positive number");

  await page.getByLabel("Description").fill("Parking");

  for (const value of ["", "0", "-4", "abc"]) {
    await amount.fill(value);
    await amount.blur();
    await expect(error).toBeVisible();

    await add.click();
    await page.reload();
    await expect(page.getByRole("list", { name: "Expenses" }).getByRole("listitem")).toHaveCount(0);

    await page.getByLabel("Description").fill("Parking");
  }

  await amount.fill("4.25");
  await expect(error).toBeHidden();
  await add.click();

  await expect(page.getByRole("list", { name: "Expenses" }).getByRole("listitem")).toHaveText([
    "Parking $4.25EditDelete",
  ]);
});

test("edits an expense amount in place and persists the updated total", async ({ page }) => {
  await addExpense(page, "Dinner", "20");
  await addExpense(page, "Taxi", "8");

  const update = page.waitForRequest((req) => req.method() === "PATCH" && /\/api\/expenses\/\d+$/.test(req.url()));
  await page.getByRole("button", { name: "Edit Dinner" }).click();
  await page.getByLabel("New amount for Dinner").fill("24.75");
  await page.getByRole("button", { name: "Save Dinner" }).click();
  await update;

  await expect(page.getByRole("listitem").filter({ hasText: "Dinner" })).toHaveText("Dinner $24.75EditDelete");
  await expect(page.getByText("Total: $32.75")).toBeVisible();

  await page.reload();
  await expect(page.getByRole("listitem").filter({ hasText: "Dinner" })).toHaveText("Dinner $24.75EditDelete");
  await expect(page.getByText("Total: $32.75")).toBeVisible();
});

test("deletes an expense and keeps it deleted after reload", async ({ page }) => {
  await addExpense(page, "Books", "9");
  await addExpense(page, "Snacks", "6.5");

  const removal = page.waitForRequest((req) => req.method() === "DELETE" && /\/api\/expenses\/\d+$/.test(req.url()));
  await page.getByRole("button", { name: "Delete Books" }).click();
  await removal;

  await expect(page.getByRole("listitem").filter({ hasText: "Books" })).toHaveCount(0);
  await expect(page.getByRole("listitem").filter({ hasText: "Snacks" })).toHaveText("Snacks $6.50EditDelete");
  await expect(page.getByText("Total: $6.50")).toBeVisible();

  await page.reload();
  await expect(page.getByRole("listitem").filter({ hasText: "Books" })).toHaveCount(0);
  await expect(page.getByRole("listitem").filter({ hasText: "Snacks" })).toHaveText("Snacks $6.50EditDelete");
  await expect(page.getByText("Total: $6.50")).toBeVisible();
});
