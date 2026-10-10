import { expect, test } from "@playwright/test";

const ERROR = "Amount must be a positive number";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBe(true);
  await page.goto("/");
});

async function add(page, description, amount) {
  await page.getByLabel("Description").fill(description);
  await page.getByLabel("Amount").fill(amount);
  await page.getByRole("button", { name: "Add", exact: true }).click();
}

const items = (page) => page.getByRole("list", { name: "Expenses" }).getByRole("listitem");

test("adds expenses newest first with formatted amounts and total", async ({ page }) => {
  await expect(page.locator("#ex-total")).toHaveText("Total: $0.00");

  await add(page, "Lunch", "12.5");
  await expect(items(page)).toHaveCount(1);
  await expect(items(page).first()).toContainText("Lunch");
  await expect(items(page).first()).toContainText("$12.50");
  await expect(page.locator("#ex-total")).toHaveText("Total: $12.50");

  await add(page, "Coffee", "3");
  await expect(items(page)).toHaveCount(2);
  await expect(items(page).nth(0)).toContainText("Coffee");
  await expect(items(page).nth(0)).toContainText("$3.00");
  await expect(items(page).nth(1)).toContainText("Lunch");
  await expect(page.locator("#ex-total")).toHaveText("Total: $15.50");
  await expect(page.getByLabel("Description")).toHaveValue("");
  await expect(page.getByLabel("Amount")).toHaveValue("");
});

for (const [name, value] of [
  ["empty", ""],
  ["zero", "0"],
  ["negative", "-5"],
  ["not a number", "abc"],
]) {
  test(`invalid amount (${name}) shows an error on blur and refuses Add`, async ({ page, request }) => {
    const amount = page.getByLabel("Amount");
    const error = page.getByText(ERROR);

    await amount.fill(value);
    await expect(error).toBeHidden();
    await page.getByLabel("Description").click(); // moves focus out of Amount
    await expect(error).toBeVisible();

    await page.getByLabel("Description").fill("Taxi");
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(error).toBeVisible();
    await expect(items(page)).toHaveCount(0);
    await expect(page.locator("#ex-total")).toHaveText("Total: $0.00");
    expect(await (await request.get("/api/expenses")).json()).toEqual([]);

    await amount.fill("8.25");
    await expect(error).toBeHidden();
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(items(page)).toHaveCount(1);
    await expect(items(page).first()).toContainText("$8.25");
  });
}

test("edits an expense amount in place and the total follows", async ({ page }) => {
  await add(page, "Lunch", "10");
  await expect(items(page)).toHaveCount(1);
  await add(page, "Coffee", "4");
  await expect(items(page)).toHaveCount(2);
  await expect(page.locator("#ex-total")).toHaveText("Total: $14.00");

  await page.getByRole("button", { name: "Edit Lunch" }).click();
  await page.getByLabel("New amount for Lunch").fill("25.75");
  await page.getByRole("button", { name: "Save Lunch" }).click();

  await expect(items(page)).toHaveCount(2);
  await expect(items(page).nth(1)).toContainText("Lunch");
  await expect(items(page).nth(1)).toContainText("$25.75");
  await expect(page.locator("#ex-total")).toHaveText("Total: $29.75");
});

test("deletes an expense", async ({ page }) => {
  await add(page, "Lunch", "10");
  await expect(items(page)).toHaveCount(1);
  await add(page, "Coffee", "4");
  await expect(items(page)).toHaveCount(2);

  await page.getByRole("button", { name: "Delete Coffee" }).click();
  await expect(items(page)).toHaveCount(1);
  await expect(items(page).first()).toContainText("Lunch");
  await expect(page.locator("#ex-total")).toHaveText("Total: $10.00");
});

test("expenses, edits and deletions survive a reload", async ({ page }) => {
  await add(page, "Lunch", "10");
  await expect(items(page)).toHaveCount(1);
  await add(page, "Coffee", "4");
  await expect(items(page)).toHaveCount(2);
  await add(page, "Taxi", "20");
  await expect(items(page)).toHaveCount(3);

  await page.getByRole("button", { name: "Edit Lunch" }).click();
  await page.getByLabel("New amount for Lunch").fill("11.5");
  await page.getByRole("button", { name: "Save Lunch" }).click();
  await expect(items(page).nth(2)).toContainText("$11.50");

  await page.getByRole("button", { name: "Delete Coffee" }).click();
  await expect(items(page)).toHaveCount(2);
  await expect(page.locator("#ex-total")).toHaveText("Total: $31.50");

  await page.reload();
  await expect(items(page)).toHaveCount(2);
  await expect(items(page).nth(0)).toContainText("Taxi");
  await expect(items(page).nth(0)).toContainText("$20.00");
  await expect(items(page).nth(1)).toContainText("Lunch");
  await expect(items(page).nth(1)).toContainText("$11.50");
  await expect(page.getByText("Coffee")).toHaveCount(0);
  await expect(page.locator("#ex-total")).toHaveText("Total: $31.50");
});
