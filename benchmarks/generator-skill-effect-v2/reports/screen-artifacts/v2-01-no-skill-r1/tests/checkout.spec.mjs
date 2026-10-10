import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

async function fillAddress(page, city = "Springfield") {
  await page.getByLabel("Full name").fill("Ada Lovelace");
  await page.getByLabel("Street").fill("1 Analytical Way");
  await page.getByLabel("City").fill(city);
  await page.getByRole("button", { name: "Next" }).click();
}

async function chooseMethod(page, label) {
  await expect(page.getByRole("heading", { name: "Shipping method" })).toBeVisible();
  await page.getByLabel(label).check();
  await page.getByRole("button", { name: "Next" }).click();
}

test("places an order with standard shipping", async ({ page }) => {
  await fillAddress(page);
  await chooseMethod(page, /Standard/);

  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
  const items = page.getByRole("list", { name: "Items" });
  await expect(items.getByRole("listitem")).toHaveText(["Desk lamp — $40.00", "Notebook — $8.00"]);
  await expect(page.locator("#co-shipping-line")).toHaveText("Shipping (Standard): $5.00");
  await expect(page.locator("#co-total")).toHaveText("Total: $53.00");

  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");
  const orders = page.getByRole("list", { name: "Your orders" });
  await expect(orders.getByRole("listitem")).toHaveText(["Order #1001 — $53.00 — Springfield"]);

  await page.reload();
  await expect(orders.getByRole("listitem")).toHaveText(["Order #1001 — $53.00 — Springfield"]);
});

test("express shipping updates the review and total", async ({ page }) => {
  await fillAddress(page);
  await chooseMethod(page, /Express/);

  await expect(page.locator("#co-shipping-line")).toHaveText("Shipping (Express): $15.00");
  await expect(page.locator("#co-total")).toHaveText("Total: $63.00");

  await page.getByRole("button", { name: "Confirm order" }).click();
  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveText([
    "Order #1001 — $63.00 — Springfield",
  ]);
});

test("going back keeps the address and shipping method", async ({ page }) => {
  await fillAddress(page);
  await chooseMethod(page, /Express/);

  await page.getByRole("button", { name: "Back" }).click();
  await expect(page.getByRole("heading", { name: "Shipping method" })).toBeVisible();
  await expect(page.getByLabel(/Express/)).toBeChecked();

  await page.getByRole("button", { name: "Back" }).click();
  await expect(page.getByLabel("Full name")).toHaveValue("Ada Lovelace");
  await expect(page.getByLabel("Street")).toHaveValue("1 Analytical Way");
  await expect(page.getByLabel("City")).toHaveValue("Springfield");

  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.locator("#co-total")).toHaveText("Total: $63.00");
});

test("a declined payment stays on review and orders nothing", async ({ page, request }) => {
  await fillAddress(page, "Failville");
  await chooseMethod(page, /Standard/);
  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.getByRole("alert").filter({ hasText: "Payment declined" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Thank you" })).toBeHidden();
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveCount(0);
  expect(await (await request.get("/api/orders")).json()).toEqual([]);
});

test("a shopper can retry with a new city after a decline", async ({ page }) => {
  await fillAddress(page, "Failville");
  await chooseMethod(page, /Standard/);
  await page.getByRole("button", { name: "Confirm order" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Payment declined" })).toBeVisible();

  await page.getByRole("button", { name: "Back" }).click();
  await page.getByRole("button", { name: "Back" }).click();
  await page.getByLabel("City").fill("Springfield");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");
});
