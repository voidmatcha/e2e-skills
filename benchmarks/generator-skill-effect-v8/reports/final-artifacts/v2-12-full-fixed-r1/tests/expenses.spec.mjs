import { expect, test } from "@playwright/test";

const resetExpenses = async (request) => {
  const response = await request.post("/api/reset");
  await expect(response).toBeOK();
};

const gotoExpenses = async (page) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Expenses", exact: true })).toBeVisible();
};

const addExpense = async (page, description, amount) => {
  await page.getByLabel("Description").fill(description);
  await page.getByLabel("Amount").fill(String(amount));

  const createRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/expenses",
  );
  await page.getByRole("button", { name: "Add", exact: true }).click();
  const request = await createRequest;
  expect(request.postDataJSON()).toEqual({ description, amount: Number(amount) });
};

test.beforeEach(async ({ request }) => {
  await resetExpenses(request);
});

test("adds expenses newest first and keeps the formatted total after reload", async ({ page }) => {
  await gotoExpenses(page);

  await addExpense(page, "Coffee", 12.5);
  await expect(page.getByText("Total: $12.50")).toBeVisible();

  await addExpense(page, "Bus", 3.25);

  const expenses = page.getByRole("list", { name: "Expenses", exact: true }).getByRole("listitem");
  await expect(expenses).toHaveText([
    /Bus\s+\$3\.25EditDelete/,
    /Coffee\s+\$12\.50EditDelete/,
  ]);
  await expect(page.getByText("Total: $15.75")).toBeVisible();

  await page.reload();
  await expect(expenses).toHaveText([
    /Bus\s+\$3\.25EditDelete/,
    /Coffee\s+\$12\.50EditDelete/,
  ]);
  await expect(page.getByText("Total: $15.75")).toBeVisible();
});

test("refuses invalid amounts until the amount is fixed", async ({ page }) => {
  await gotoExpenses(page);

  const description = page.getByLabel("Description");
  const amount = page.getByLabel("Amount");
  const error = page.getByText("Amount must be a positive number");
  const expenses = page.getByRole("list", { name: "Expenses", exact: true }).getByRole("listitem");

  for (const invalidAmount of ["", "0", "-1", "not a number"]) {
    await description.fill(`Invalid ${invalidAmount || "empty"}`);
    await amount.fill(invalidAmount);
    await description.click();
    await expect(error).toBeVisible();

    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(expenses).toHaveCount(0);
    await expect(page.getByText("Total: $0.00")).toBeVisible();
  }

  await amount.fill("4.5");
  await expect(error).toBeHidden();

  await addExpense(page, "Fixed amount", 4.5);
  await expect(expenses).toHaveText([/Fixed amount\s+\$4\.50EditDelete/]);
  await expect(page.getByText("Total: $4.50")).toBeVisible();
});

test("edits an expense amount in place and persists the changed total", async ({ page }) => {
  await gotoExpenses(page);
  await addExpense(page, "Lunch", 6);

  await page.getByRole("button", { name: "Edit Lunch", exact: true }).click();
  await page.getByLabel("New amount for Lunch").fill("8.75");

  const updateRequest = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      /\/api\/expenses\/\d+$/.test(new URL(request.url()).pathname),
  );
  await page.getByRole("button", { name: "Save Lunch", exact: true }).click();
  const request = await updateRequest;
  expect(request.postDataJSON()).toEqual({ amount: 8.75 });

  const lunch = page.getByRole("listitem").filter({ hasText: "Lunch" });
  await expect(lunch).toContainText("$8.75");
  await expect(page.getByText("Total: $8.75")).toBeVisible();

  await page.reload();
  await expect(lunch).toContainText("$8.75");
  await expect(page.getByText("Total: $8.75")).toBeVisible();
});

test("deletes an expense and keeps it removed after reload", async ({ page }) => {
  await gotoExpenses(page);
  await addExpense(page, "Notebook", 9.99);

  const notebook = page.getByRole("listitem").filter({ hasText: "Notebook" });
  await expect(notebook).toContainText("$9.99");

  const deleteRequest = page.waitForRequest(
    (request) =>
      request.method() === "DELETE" &&
      /\/api\/expenses\/\d+$/.test(new URL(request.url()).pathname),
  );
  await page.getByRole("button", { name: "Delete Notebook", exact: true }).click();
  await deleteRequest;

  await expect(notebook).not.toBeAttached();
  await expect(page.getByText("Total: $0.00")).toBeVisible();

  await page.reload();
  await expect(page.getByRole("list", { name: "Expenses", exact: true }).getByRole("listitem")).toHaveCount(0);
  await expect(page.getByText("Total: $0.00")).toBeVisible();
});
