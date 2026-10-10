import { expect, test } from "@playwright/test";

const address = { name: "Ada Lovelace", street: "1 Main St", city: "Springfield" };

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
});

async function fillAddress(page, { name, street, city } = address) {
  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Street").fill(street);
  await page.getByLabel("City").fill(city);
  await page.getByRole("button", { name: "Next" }).click();
}

async function chooseMethod(page, label) {
  await page.getByRole("radio", { name: label }).check();
  await page.getByRole("button", { name: "Next" }).click();
}

test("starts on the shipping step with an empty order history", async ({ page }) => {
  await expect(page.locator("#co-step")).toHaveText("Step 1 of 3");
  await expect(page.getByRole("heading", { name: "Shipping address" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveCount(0);
});

for (const { label, shipping, total } of [
  { label: "Standard", shipping: "$5.00", total: "$53.00" },
  { label: "Express", shipping: "$15.00", total: "$63.00" },
]) {
  test(`${label} shipping: review shows items, shipping cost and total`, async ({ page }) => {
    await fillAddress(page);
    await expect(page.locator("#co-step")).toHaveText("Step 2 of 3");
    await chooseMethod(page, new RegExp(`^${label}`));

    await expect(page.locator("#co-step")).toHaveText("Step 3 of 3");
    const items = page.getByRole("list", { name: "Items" }).getByRole("listitem");
    await expect(items).toHaveText(["Desk lamp — $40.00", "Notebook — $8.00"]);
    await expect(page.locator("#co-shipping-line")).toHaveText(`Shipping (${label}): ${shipping}`);
    await expect(page.locator("#co-total")).toHaveText(`Total: ${total}`);
  });
}

test("confirming shows the order number and lists the order, also after reload", async ({ page }) => {
  await fillAddress(page);
  await chooseMethod(page, /^Express/);
  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.locator("#co-step")).toHaveText("Order placed");
  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");
  const orders = page.getByRole("list", { name: "Your orders" }).getByRole("listitem");
  await expect(orders).toHaveText(["Order #1001 — $63.00 — Springfield"]);

  await page.reload();
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveText([
    "Order #1001 — $63.00 — Springfield",
  ]);
});

test("a second order gets the next number and both are listed", async ({ page }) => {
  for (const method of [/^Standard/, /^Express/]) {
    await page.goto("/");
    await fillAddress(page);
    await chooseMethod(page, method);
    await page.getByRole("button", { name: "Confirm order" }).click();
    await expect(page.locator("#co-step")).toHaveText("Order placed");
  }
  await expect(page.getByRole("status")).toHaveText("Order #1002 confirmed");
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveText([
    "Order #1001 — $53.00 — Springfield",
    "Order #1002 — $63.00 — Springfield",
  ]);
});

test("going back keeps what the shopper typed and chose", async ({ page }) => {
  await fillAddress(page);
  await chooseMethod(page, /^Express/);

  // review -> method: the chosen method is still selected
  await page.getByRole("button", { name: "Back" }).and(page.locator("#co-review-back")).click();
  await expect(page.locator("#co-step")).toHaveText("Step 2 of 3");
  await expect(page.getByRole("radio", { name: /^Express/ })).toBeChecked();

  // method -> shipping: the address is still filled in
  await page.getByRole("button", { name: "Back" }).and(page.locator("#co-method-back")).click();
  await expect(page.locator("#co-step")).toHaveText("Step 1 of 3");
  await expect(page.getByLabel("Full name")).toHaveValue(address.name);
  await expect(page.getByLabel("Street")).toHaveValue(address.street);
  await expect(page.getByLabel("City")).toHaveValue(address.city);

  // moving forward again still yields a correct review and order
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.locator("#co-total")).toHaveText("Total: $63.00");
  await page.getByRole("button", { name: "Confirm order" }).click();
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveText([
    "Order #1001 — $63.00 — Springfield",
  ]);
});

test("a declined payment stays on review, shows the error and orders nothing", async ({ page }) => {
  await fillAddress(page, { ...address, city: "Failville" });
  await chooseMethod(page, /^Standard/);
  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.getByRole("alert")).toHaveText("Payment declined");
  await expect(page.locator("#co-step")).toHaveText("Step 3 of 3");
  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Thank you" })).toBeHidden();
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveCount(0);
  const orders = await page.request.get("/api/orders");
  expect(await orders.json()).toEqual([]);
});

test("after a decline the shopper can fix the city and order successfully", async ({ page }) => {
  await fillAddress(page, { ...address, city: "Failville" });
  await chooseMethod(page, /^Standard/);
  await page.getByRole("button", { name: "Confirm order" }).click();
  await expect(page.getByRole("alert")).toHaveText("Payment declined");

  await page.locator("#co-review-back").click();
  await page.locator("#co-method-back").click();
  await page.getByLabel("City").fill("Springfield");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Confirm order" }).click();

  // the declined attempt did not consume an order number
  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveCount(1);
});
