import { expect, test } from "@playwright/test";

const address = { name: "Ada Lovelace", street: "1 Analytical Way", city: "London" };

test.beforeEach(async ({ request, page }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBe(true);
  await page.goto("/");
});

async function fillAddress(page, { name, street, city }) {
  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Street").fill(street);
  await page.getByLabel("City").fill(city);
  await page.getByRole("button", { name: "Next" }).click();
}

async function chooseMethod(page, label) {
  await page.getByLabel(label).check();
  await page.getByRole("button", { name: "Next" }).click();
}

test("places an order with standard shipping", async ({ page }) => {
  await fillAddress(page, address);
  await expect(page.getByRole("heading", { name: "Shipping method" })).toBeVisible();
  await chooseMethod(page, /Standard/);

  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
  const items = page.getByRole("list", { name: "Items" });
  await expect(items.getByRole("listitem")).toHaveText(["Desk lamp — $40.00", "Notebook — $8.00"]);
  await expect(page.getByText("Shipping (Standard): $5.00")).toBeVisible();
  await expect(page.getByText("Total: $53.00")).toBeVisible();

  await page.getByRole("button", { name: "Confirm order" }).click();
  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");

  const orders = page.getByRole("list", { name: "Your orders" });
  await expect(orders.getByRole("listitem")).toHaveText(["Order #1001 — $53.00 — London"]);

  await page.reload();
  await expect(orders.getByRole("listitem")).toHaveText(["Order #1001 — $53.00 — London"]);
});

test("express shipping changes the shipping cost and total", async ({ page }) => {
  await fillAddress(page, address);
  await chooseMethod(page, /Express/);

  await expect(page.getByText("Shipping (Express): $15.00")).toBeVisible();
  await expect(page.getByText("Total: $63.00")).toBeVisible();

  await page.getByRole("button", { name: "Confirm order" }).click();
  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveText([
    "Order #1001 — $63.00 — London",
  ]);
});

test("going back keeps the typed address and chosen method", async ({ page }) => {
  await fillAddress(page, address);
  await chooseMethod(page, /Express/);
  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();

  await page.getByRole("button", { name: "Back" }).click();
  await expect(page.getByRole("heading", { name: "Shipping method" })).toBeVisible();
  await expect(page.getByLabel(/Express/)).toBeChecked();

  await page.getByRole("button", { name: "Back" }).click();
  await expect(page.getByRole("heading", { name: "Shipping address" })).toBeVisible();
  await expect(page.getByLabel("Full name")).toHaveValue(address.name);
  await expect(page.getByLabel("Street")).toHaveValue(address.street);
  await expect(page.getByLabel("City")).toHaveValue(address.city);

  // Moving forward again still reaches review with the same choices.
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Total: $63.00")).toBeVisible();
});

test("a declined payment keeps the shopper on review and orders nothing", async ({ page, request }) => {
  await fillAddress(page, { ...address, city: "Failville" });
  await chooseMethod(page, /Standard/);
  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.getByRole("alert")).toHaveText("Payment declined");
  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm order" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Thank you" })).toBeHidden();
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveCount(0);

  const orders = await (await request.get("/api/orders")).json();
  expect(orders).toEqual([]);

  await page.reload();
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveCount(0);
});
