import { expect, test } from "@playwright/test";

const orders = (page) => page.getByRole("list", { name: "Your orders" }).getByRole("listitem");

async function address(page, city = "Springfield") {
  await page.getByLabel("Full name").fill("Ada Lovelace");
  await page.getByLabel("Street").fill("1 Analytical Way");
  await page.getByLabel("City").fill(city);
  await page.getByRole("button", { name: "Next" }).click();
}

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("review shows items, shipping and total for the chosen method", async ({ page }) => {
  await address(page);
  await page.getByLabel("Express ($15.00)").check();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByRole("list", { name: "Items" }).getByRole("listitem")).toHaveText(["Desk lamp — $40.00", "Notebook — $8.00"]);
  await expect(page.getByText("Shipping (Express): $15.00")).toBeVisible();
  await expect(page.getByText("Total: $63.00")).toBeVisible();
});

test("confirming shows the order number and stores the order", async ({ page }) => {
  await address(page);
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Total: $53.00")).toBeVisible();
  await page.getByRole("button", { name: "Confirm order" }).click();
  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");
  await expect(orders(page)).toHaveText([/Order #1001/]);
  await page.reload();
  await expect(orders(page)).toHaveText([/Order #1001 — \$53\.00 — Springfield/]);
});

test("going back keeps the typed address", async ({ page }) => {
  await address(page);
  await page.getByRole("button", { name: "Back" }).click();
  await expect(page.getByLabel("Full name")).toHaveValue("Ada Lovelace");
  await expect(page.getByLabel("Street")).toHaveValue("1 Analytical Way");
  await expect(page.getByLabel("City")).toHaveValue("Springfield");
});

test("a declined payment keeps the shopper on review and orders nothing", async ({ page }) => {
  await address(page, "Failville");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Confirm order" }).click();
  await expect(page.getByRole("alert")).toHaveText("Payment declined");
  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
  await expect(orders(page)).toHaveCount(0);
  await page.reload();
  await expect(orders(page)).toHaveCount(0);
});
