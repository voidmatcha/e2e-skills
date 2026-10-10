import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

const addExpense = async (page, description, amount) => {
  await page.getByLabel("Description").fill(description);
  await page.getByLabel("Amount").fill(amount);

  const created = page.waitForRequest((request) => {
    if (request.method() !== "POST" || !request.url().endsWith("/api/expenses")) return false;
    const body = request.postDataJSON();
    return body.description === description && body.amount === Number(amount);
  });

  await page.getByRole("button", { name: "Add" }).click();
  await created;
};

test("adds expenses newest first, updates the total, and persists after reload", async ({ page }) => {
  await addExpense(page, "Coffee", "4.25");
  await addExpense(page, "Lunch", "12.5");

  const expenses = page.getByRole("list", { name: "Expenses" }).getByRole("listitem");
  await expect(expenses).toHaveCount(2);
  await expect(expenses).toHaveText([/Lunch \$12\.50/, /Coffee \$4\.25/]);
  await expect(page.getByText("Total: $16.75")).toBeVisible();

  await page.reload();

  await expect(expenses).toHaveText([/Lunch \$12\.50/, /Coffee \$4\.25/]);
  await expect(page.getByText("Total: $16.75")).toBeVisible();
});

test("refuses invalid amounts until the amount is fixed", async ({ page }) => {
  const invalidAmounts = ["", "0", "-3", "abc"];
  let unexpectedPost = false;

  await page.route("**/api/expenses", async (route) => {
    if (route.request().method() === "POST") {
      unexpectedPost = true;
      await route.abort();
      return;
    }

    await route.continue();
  });

  for (const amount of invalidAmounts) {
    unexpectedPost = false;
    await page.getByLabel("Description").fill(`Invalid ${amount || "empty"}`);
    await page.getByLabel("Amount").fill(amount);
    await page.getByLabel("Description").focus();

    await expect(page.getByText("Amount must be a positive number")).toBeVisible();

    await page.getByRole("button", { name: "Add" }).click();
    await expect(page.getByRole("list", { name: "Expenses" }).getByRole("listitem")).toHaveCount(0);
    expect(unexpectedPost).toBe(false);
  }

  await page.unroute("**/api/expenses");
  await addExpense(page, "Fixed amount", "8");

  await expect(page.getByRole("listitem").filter({ hasText: "Fixed amount $8.00" })).toBeVisible();
  await expect(page.getByText("Total: $8.00")).toBeVisible();
});

test("edits an expense amount in place and persists the changed total", async ({ page }) => {
  await addExpense(page, "Taxi", "10");

  await page.getByRole("button", { name: "Edit Taxi" }).click();
  await page.getByLabel("New amount for Taxi").fill("14.75");

  const updated = page.waitForRequest((request) => {
    if (request.method() !== "PATCH" || !request.url().match(/\/api\/expenses\/\d+$/)) return false;
    return request.postDataJSON().amount === 14.75;
  });

  await page.getByRole("button", { name: "Save Taxi" }).click();
  await updated;

  await expect(page.getByRole("listitem").filter({ hasText: "Taxi $14.75" })).toBeVisible();
  await expect(page.getByText("Total: $14.75")).toBeVisible();

  await page.reload();

  await expect(page.getByRole("listitem").filter({ hasText: "Taxi $14.75" })).toBeVisible();
  await expect(page.getByText("Total: $14.75")).toBeVisible();
});

test("deletes an expense and keeps it deleted after reload", async ({ page }) => {
  await addExpense(page, "Book", "9.99");
  await addExpense(page, "Snack", "2.50");

  const deleted = page.waitForRequest((request) => {
    return request.method() === "DELETE" && request.url().match(/\/api\/expenses\/\d+$/);
  });

  await page.getByRole("button", { name: "Delete Book" }).click();
  await deleted;

  await expect(page.getByRole("listitem").filter({ hasText: "Book $9.99" })).toHaveCount(0);
  await expect(page.getByRole("listitem").filter({ hasText: "Snack $2.50" })).toBeVisible();
  await expect(page.getByText("Total: $2.50")).toBeVisible();

  await page.reload();

  await expect(page.getByRole("listitem").filter({ hasText: "Book $9.99" })).toHaveCount(0);
  await expect(page.getByRole("listitem").filter({ hasText: "Snack $2.50" })).toBeVisible();
  await expect(page.getByText("Total: $2.50")).toBeVisible();
});
