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
}

test("adds expenses newest first with formatted amounts and total", async ({ page }) => {
  await addExpense(page, "Coffee", "12.5");
  await expect(page.getByText("Total: $12.50")).toBeVisible();
  await addExpense(page, "Lunch", "7");

  const items = page.getByRole("list", { name: "Expenses" }).getByRole("listitem");
  await expect(items).toHaveCount(2);
  await expect(items.nth(0)).toContainText("Lunch");
  await expect(items.nth(0)).toContainText("$7.00");
  await expect(items.nth(1)).toContainText("Coffee");
  await expect(items.nth(1)).toContainText("$12.50");
  await expect(page.locator("#ex-total")).toHaveText("Total: $19.50");
  await expect(page.getByLabel("Description")).toHaveValue("");
  await expect(page.getByLabel("Amount")).toHaveValue("");
});

for (const [name, value] of [
  ["empty", ""],
  ["zero", "0"],
  ["negative", "-5"],
  ["not a number", "abc"],
]) {
  test(`rejects ${name} amount on blur and refuses Add`, async ({ page, request }) => {
    const error = page.getByRole("alert").filter({ hasText: ERROR });
    await page.getByLabel("Description").fill("Bad");
    await page.getByLabel("Amount").fill(value);
    await expect(error).toHaveCount(0);
    await page.getByLabel("Description").focus();
    await expect(error).toBeVisible();

    await page.getByRole("button", { name: "Add" }).click();
    await expect(error).toBeVisible();
    await expect(page.getByRole("listitem")).toHaveCount(0);
    expect(await (await request.get("/api/expenses")).json()).toEqual([]);

    await page.getByLabel("Amount").fill("3");
    await expect(error).toHaveCount(0);
    await page.getByRole("button", { name: "Add" }).click();
    await expect(page.getByRole("listitem")).toHaveCount(1);
    await expect(page.locator("#ex-total")).toHaveText("Total: $3.00");
  });
}

test("edits an amount in place and the total follows", async ({ page }) => {
  await addExpense(page, "Coffee", "10");
  await addExpense(page, "Lunch", "5");
  await expect(page.locator("#ex-total")).toHaveText("Total: $15.00");

  await page.getByRole("button", { name: "Edit Coffee" }).click();
  await page.getByLabel("New amount for Coffee").fill("2.25");
  await page.getByRole("button", { name: "Save Coffee" }).click();

  const coffee = page.getByRole("listitem").filter({ hasText: "Coffee" });
  await expect(coffee).toContainText("$2.25");
  await expect(page.locator("#ex-total")).toHaveText("Total: $7.25");
  await expect(page.getByRole("listitem")).toHaveCount(2);
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
  await addExpense(page, "Taxi", "20");
  await page.getByRole("button", { name: "Edit Coffee" }).click();
  await page.getByLabel("New amount for Coffee").fill("11");
  await page.getByRole("button", { name: "Save Coffee" }).click();
  await expect(page.locator("#ex-total")).toHaveText("Total: $36.00");
  await page.getByRole("button", { name: "Delete Lunch" }).click();
  await expect(page.locator("#ex-total")).toHaveText("Total: $31.00");

  await page.reload();

  const items = page.getByRole("listitem");
  await expect(items).toHaveCount(2);
  await expect(items.nth(0)).toContainText("Taxi");
  await expect(items.nth(0)).toContainText("$20.00");
  await expect(items.nth(1)).toContainText("Coffee");
  await expect(items.nth(1)).toContainText("$11.00");
  await expect(page.locator("#ex-total")).toHaveText("Total: $31.00");
});
