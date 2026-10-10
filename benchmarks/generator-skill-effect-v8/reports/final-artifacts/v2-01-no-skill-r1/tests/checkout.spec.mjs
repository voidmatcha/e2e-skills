import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shopper completes checkout and sees the order after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Full name").fill("Ada Lovelace");
  await page.getByLabel("Street").fill("12 Algorithm Ave");
  await page.getByLabel("City").fill("London");
  await page.getByRole("button", { name: "Next" }).click();

  await expect(page.getByText("Step 2 of 3")).toBeVisible();
  await page.getByRole("button", { name: "Back" }).click();
  await expect(page.getByLabel("Full name")).toHaveValue("Ada Lovelace");
  await expect(page.getByLabel("Street")).toHaveValue("12 Algorithm Ave");
  await expect(page.getByLabel("City")).toHaveValue("London");

  await page.getByRole("button", { name: "Next" }).click();
  await page.getByLabel("Express ($15.00)").check();
  await page.getByRole("button", { name: "Next" }).click();

  await expect(page.getByText("Step 3 of 3")).toBeVisible();
  await expect(page.getByRole("list", { name: "Items" })).toContainText("Desk lamp — $40.00");
  await expect(page.getByRole("list", { name: "Items" })).toContainText("Notebook — $8.00");
  await expect(page.locator("#co-shipping-line")).toHaveText("Shipping (Express): $15.00");
  await expect(page.locator("#co-total")).toHaveText("Total: $63.00");

  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");
  await expect(page.getByRole("list", { name: "Your orders" })).toContainText(
    "Order #1001 — $63.00 — London",
  );

  await page.reload();
  await expect(page.getByRole("list", { name: "Your orders" })).toContainText(
    "Order #1001 — $63.00 — London",
  );
});

test("shopper stays on review and no order is created when payment is declined", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Full name").fill("Grace Hopper");
  await page.getByLabel("Street").fill("404 Compiler Way");
  await page.getByLabel("City").fill("Failville");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();

  await expect(page.getByText("Step 3 of 3")).toBeVisible();
  await expect(page.locator("#co-shipping-line")).toHaveText("Shipping (Standard): $5.00");
  await expect(page.locator("#co-total")).toHaveText("Total: $53.00");

  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.getByRole("alert")).toHaveText("Payment declined");
  await expect(page.getByText("Step 3 of 3")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Thank you" })).toBeHidden();
  await expect(page.getByRole("list", { name: "Your orders" })).toBeEmpty();

  await page.reload();
  await expect(page.getByRole("list", { name: "Your orders" })).toBeEmpty();
});
