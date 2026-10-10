import { expect, test } from "@playwright/test";

const address = { name: "Ada Lovelace", street: "1 Analytical Way", city: "London" };

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
});

async function fillAddress(page, { name, street, city }) {
  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Street").fill(street);
  await page.getByLabel("City").fill(city);
  await page.getByRole("button", { name: "Next" }).click();
}

async function chooseMethod(page, label) {
  await page.getByRole("radio", { name: label }).check();
  await page.getByRole("button", { name: "Next" }).click();
}

test("review shows items, standard shipping and total", async ({ page }) => {
  await fillAddress(page, address);
  await chooseMethod(page, /Standard/);

  await expect(page.getByText("Step 3 of 3")).toBeVisible();
  const items = page.getByRole("list", { name: "Items" }).getByRole("listitem");
  await expect(items).toHaveText(["Desk lamp — $40.00", "Notebook — $8.00"]);
  await expect(page.getByText("Shipping (Standard): $5.00")).toBeVisible();
  await expect(page.getByText("Total: $53.00")).toBeVisible();
});

test("review shows express shipping cost and total", async ({ page }) => {
  await fillAddress(page, address);
  await chooseMethod(page, /Express/);

  await expect(page.getByText("Shipping (Express): $15.00")).toBeVisible();
  await expect(page.getByText("Total: $63.00")).toBeVisible();
});

test("confirming shows the order number and lists the order, also after reload", async ({ page }) => {
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveCount(0);

  await fillAddress(page, address);
  await chooseMethod(page, /Express/);
  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");
  const orders = page.getByRole("list", { name: "Your orders" }).getByRole("listitem");
  await expect(orders).toHaveText(["Order #1001 — $63.00 — London"]);

  await page.reload();
  await expect(orders).toHaveText(["Order #1001 — $63.00 — London"]);
});

test("going back keeps what the shopper typed and the chosen method", async ({ page }) => {
  await fillAddress(page, address);
  await chooseMethod(page, /Express/);
  await page.getByRole("button", { name: "Back" }).click();
  await expect(page.getByRole("radio", { name: /Express/ })).toBeChecked();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Back" }).click();
  await page.getByRole("button", { name: "Back" }).click();

  await expect(page.getByText("Step 1 of 3")).toBeVisible();
  await expect(page.getByLabel("Full name")).toHaveValue(address.name);
  await expect(page.getByLabel("Street")).toHaveValue(address.street);
  await expect(page.getByLabel("City")).toHaveValue(address.city);
});

test("declined payment keeps the shopper on review and orders nothing", async ({ page }) => {
  await fillAddress(page, { ...address, city: "Failville" });
  await chooseMethod(page, /Standard/);
  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.getByRole("alert")).toHaveText("Payment declined");
  await expect(page.getByText("Step 3 of 3")).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm order" })).toBeVisible();
  await expect(page.getByRole("status")).toBeHidden();
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveCount(0);
});

test("a declined payment does not consume an order number", async ({ page }) => {
  await fillAddress(page, { ...address, city: "Failville" });
  await chooseMethod(page, /Standard/);
  await page.getByRole("button", { name: "Confirm order" }).click();
  await expect(page.getByRole("alert")).toHaveText("Payment declined");

  await page.reload();
  await fillAddress(page, address);
  await chooseMethod(page, /Standard/);
  await page.getByRole("button", { name: "Confirm order" }).click();
  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");
});
