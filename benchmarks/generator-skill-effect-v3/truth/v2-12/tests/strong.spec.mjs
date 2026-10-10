import { expect, test } from "@playwright/test";

const rows = (page) => page.getByRole("list", { name: "Expenses" }).getByRole("listitem");

async function add(page, description, amount) {
  await page.getByLabel("Description").fill(description);
  await page.getByLabel("Amount", { exact: true }).fill(amount);
  await page.getByRole("button", { name: "Add" }).click();
}

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("Total: $0.00")).toBeVisible();
});

test("adds expenses newest first with formatted amounts and a total", async ({ page }) => {
  await add(page, "Coffee", "3.5");
  await expect(rows(page)).toHaveText([/Coffee \$3\.50/]);
  await add(page, "Lunch", "12");
  await expect(rows(page)).toHaveText([/Lunch \$12\.00/, /Coffee \$3\.50/]);
  await expect(page.getByText("Total: $15.50")).toBeVisible();
  await page.reload();
  await expect(rows(page)).toHaveText([/Lunch \$12\.00/, /Coffee \$3\.50/]);
});

test("an invalid amount is flagged on blur and refused", async ({ page }) => {
  await page.getByLabel("Description").fill("Taxi");
  await page.getByLabel("Amount", { exact: true }).fill("-4");
  await expect(page.getByRole("alert")).toHaveText("");
  await page.getByLabel("Description").focus();
  await expect(page.getByRole("alert")).toHaveText("Amount must be a positive number");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(rows(page)).toHaveCount(0);
  await page.getByLabel("Amount", { exact: true }).fill("abc");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(rows(page)).toHaveCount(0);
  await page.getByLabel("Amount", { exact: true }).fill("4");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(rows(page)).toHaveText([/Taxi \$4\.00/]);
});

test("editing an amount updates the total and persists", async ({ page }) => {
  await add(page, "Books", "20");
  await add(page, "Pens", "5");
  await expect(page.getByText("Total: $25.00")).toBeVisible();
  await page.getByRole("button", { name: "Edit Books" }).click();
  await page.getByLabel("New amount for Books").fill("30");
  await page.getByRole("button", { name: "Save Books" }).click();
  await expect(rows(page)).toHaveText([/Pens \$5\.00/, /Books \$30\.00/]);
  await expect(page.getByText("Total: $35.00")).toBeVisible();
  await page.reload();
  await expect(rows(page)).toHaveText([/Pens \$5\.00/, /Books \$30\.00/]);
  await expect(page.getByText("Total: $35.00")).toBeVisible();
});

test("delete removes an expense on the server", async ({ page }) => {
  await add(page, "Snack", "2");
  await add(page, "Ticket", "9");
  await page.getByRole("button", { name: "Delete Snack" }).click();
  await expect(rows(page)).toHaveText([/Ticket \$9\.00/]);
  await expect(page.getByText("Total: $9.00")).toBeVisible();
  await page.reload();
  await expect(rows(page)).toHaveText([/Ticket \$9\.00/]);
});
