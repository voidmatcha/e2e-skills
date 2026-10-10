import { expect, test } from "@playwright/test";

const ERROR = "Amount must be a positive number";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByLabel("Description")).toBeVisible();
});

async function add(page, description, amount) {
  await page.getByLabel("Description").fill(description);
  await page.getByLabel("Amount").fill(amount);
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("list", { name: "Expenses" }).getByText(description)).toBeVisible();
}

test("adds expenses newest first with formatted amounts and total", async ({ page }) => {
  await expect(page.locator("#ex-total")).toHaveText("Total: $0.00");
  await add(page, "Lunch", "12.5");
  await add(page, "Coffee", "3");

  const items = page.getByRole("listitem");
  await expect(items).toHaveCount(2);
  await expect(items.nth(0)).toContainText("Coffee");
  await expect(items.nth(0)).toContainText("$3.00");
  await expect(items.nth(1)).toContainText("Lunch");
  await expect(items.nth(1)).toContainText("$12.50");
  await expect(page.locator("#ex-total")).toHaveText("Total: $15.50");
  await expect(page.getByLabel("Description")).toHaveValue("");
  await expect(page.getByLabel("Amount")).toHaveValue("");
});

for (const [name, value] of [["empty", ""], ["zero", "0"], ["negative", "-5"], ["non-numeric", "abc"]]) {
  test(`shows an error on blur and refuses Add for ${name} amount`, async ({ page }) => {
    await page.getByLabel("Description").fill("Taxi");
    const amount = page.getByLabel("Amount");
    await amount.fill(value);
    await expect(page.locator("#ex-amount-error")).toHaveText("");
    await amount.blur();
    await expect(page.locator("#ex-amount-error")).toHaveText(ERROR);

    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByRole("listitem")).toHaveCount(0);
    await expect(page.locator("#ex-total")).toHaveText("Total: $0.00");
    await expect(page.locator("#ex-amount-error")).toHaveText(ERROR);

    await amount.fill("4.2");
    await expect(page.locator("#ex-amount-error")).toHaveText("");
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByRole("listitem")).toHaveCount(1);
    await expect(page.getByRole("listitem")).toContainText("$4.20");
  });
}

test("edits an expense amount in place and the total follows", async ({ page }) => {
  await add(page, "Lunch", "10");
  await add(page, "Coffee", "3");
  await page.getByRole("button", { name: "Edit Lunch" }).click();
  await page.getByLabel("New amount for Lunch").fill("20.25");
  await page.getByRole("button", { name: "Save Lunch" }).click();

  await expect(page.getByRole("listitem").filter({ hasText: "Lunch" })).toContainText("$20.25");
  await expect(page.getByRole("listitem")).toHaveCount(2);
  await expect(page.locator("#ex-total")).toHaveText("Total: $23.25");
});

test("deletes an expense", async ({ page }) => {
  await add(page, "Lunch", "10");
  await add(page, "Coffee", "3");
  await page.getByRole("button", { name: "Delete Coffee" }).click();

  await expect(page.getByRole("listitem")).toHaveCount(1);
  await expect(page.getByText("Coffee")).toHaveCount(0);
  await expect(page.locator("#ex-total")).toHaveText("Total: $10.00");
});

test("expenses, edits and deletions survive a reload", async ({ page }) => {
  await add(page, "Lunch", "10");
  await add(page, "Coffee", "3");
  await add(page, "Taxi", "8");
  await page.getByRole("button", { name: "Edit Lunch" }).click();
  await page.getByLabel("New amount for Lunch").fill("11.5");
  await page.getByRole("button", { name: "Save Lunch" }).click();
  await expect(page.locator("#ex-total")).toHaveText("Total: $22.50");
  await page.getByRole("button", { name: "Delete Coffee" }).click();
  await expect(page.locator("#ex-total")).toHaveText("Total: $19.50");

  await page.reload();
  const items = page.getByRole("listitem");
  await expect(items).toHaveCount(2);
  await expect(items.nth(0)).toContainText("Taxi");
  await expect(items.nth(0)).toContainText("$8.00");
  await expect(items.nth(1)).toContainText("Lunch");
  await expect(items.nth(1)).toContainText("$11.50");
  await expect(page.getByText("Coffee")).toHaveCount(0);
  await expect(page.locator("#ex-total")).toHaveText("Total: $19.50");
});
