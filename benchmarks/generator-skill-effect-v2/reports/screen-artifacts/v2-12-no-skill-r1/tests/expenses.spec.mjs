import { expect, test } from "@playwright/test";

const ERROR = "Amount must be a positive number";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

async function add(page, description, amount) {
  await page.getByLabel("Description").fill(description);
  await page.getByLabel("Amount").fill(amount);
  await page.getByRole("button", { name: "Add" }).click();
}

const items = (page) => page.getByRole("list", { name: "Expenses" }).getByRole("listitem");

test("adds expenses newest first with formatted amounts and total", async ({ page }) => {
  await expect(page.locator("#ex-total")).toHaveText("Total: $0.00");
  await add(page, "Lunch", "12.5");
  await expect(items(page)).toHaveCount(1);
  await add(page, "Coffee", "3");
  await expect(items(page)).toHaveCount(2);
  await expect(items(page).nth(0)).toContainText("Coffee");
  await expect(items(page).nth(0)).toContainText("$3.00");
  await expect(items(page).nth(1)).toContainText("Lunch");
  await expect(items(page).nth(1)).toContainText("$12.50");
  await expect(page.locator("#ex-total")).toHaveText("Total: $15.50");
  await expect(page.getByLabel("Description")).toHaveValue("");
  await expect(page.getByLabel("Amount")).toHaveValue("");
});

for (const [name, value] of [["empty", ""], ["zero", "0"], ["negative", "-5"], ["not a number", "abc"]]) {
  test(`rejects ${name} amount on blur and on Add`, async ({ page }) => {
    const amount = page.getByLabel("Amount");
    const error = page.locator("#ex-amount-error");
    await page.getByLabel("Description").fill("Taxi");
    await amount.fill(value);
    await page.getByLabel("Description").focus();
    await expect(error).toHaveText(ERROR);

    await page.getByRole("button", { name: "Add" }).click();
    await expect(error).toHaveText(ERROR);
    await expect(items(page)).toHaveCount(0);
    await expect(page.locator("#ex-total")).toHaveText("Total: $0.00");
    expect(await (await page.request.get("/api/expenses")).json()).toEqual([]);

    await amount.fill("4.2");
    await expect(error).toHaveText("");
    await page.getByRole("button", { name: "Add" }).click();
    await expect(items(page)).toHaveCount(1);
    await expect(items(page).first()).toContainText("$4.20");
  });
}

test("edits an expense amount in place and updates the total", async ({ page }) => {
  await add(page, "Lunch", "10");
  await expect(items(page)).toHaveCount(1);
  await add(page, "Coffee", "3");
  await expect(items(page)).toHaveCount(2);
  await page.getByRole("button", { name: "Edit Lunch" }).click();
  await page.getByLabel("New amount for Lunch").fill("20.25");
  await page.getByRole("button", { name: "Save Lunch" }).click();
  await expect(items(page).nth(1)).toContainText("$20.25");
  await expect(items(page).nth(0)).toContainText("Coffee");
  await expect(page.locator("#ex-total")).toHaveText("Total: $23.25");

  await page.reload();
  await expect(items(page).nth(1)).toContainText("$20.25");
  await expect(page.locator("#ex-total")).toHaveText("Total: $23.25");
});

test("deletes an expense and the total follows", async ({ page }) => {
  await add(page, "Lunch", "10");
  await expect(items(page)).toHaveCount(1);
  await add(page, "Coffee", "3");
  await expect(items(page)).toHaveCount(2);
  await page.getByRole("button", { name: "Delete Coffee" }).click();
  await expect(items(page)).toHaveCount(1);
  await expect(items(page).first()).toContainText("Lunch");
  await expect(page.locator("#ex-total")).toHaveText("Total: $10.00");

  await page.reload();
  await expect(items(page)).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Delete Coffee" })).toHaveCount(0);
  await expect(page.locator("#ex-total")).toHaveText("Total: $10.00");
});

test("expenses persist across a reload", async ({ page }) => {
  await add(page, "Lunch", "12.5");
  await expect(items(page)).toHaveCount(1);
  await add(page, "Coffee", "3");
  await expect(items(page)).toHaveCount(2);
  await page.reload();
  await expect(items(page)).toHaveCount(2);
  await expect(items(page).nth(0)).toContainText("Coffee");
  await expect(items(page).nth(1)).toContainText("$12.50");
  await expect(page.locator("#ex-total")).toHaveText("Total: $15.50");
});
