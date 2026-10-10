import { expect, test } from "@playwright/test";

const address = { name: "Ada Lovelace", street: "12 Analytical Way", city: "London" };

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
  await page.getByLabel(label).check();
  await page.getByRole("button", { name: "Next" }).click();
}

test("starts on step 1 with no orders", async ({ page }) => {
  await expect(page.locator("#co-step")).toHaveText("Step 1 of 3");
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveCount(0);
});

for (const [label, cost, total] of [
  ["Standard", "$5.00", "$53.00"],
  ["Express", "$15.00", "$63.00"],
]) {
  test(`review shows items, ${label} shipping and total`, async ({ page }) => {
    await fillAddress(page, address);
    await chooseMethod(page, label);

    await expect(page.locator("#co-step")).toHaveText("Step 3 of 3");
    const items = page.getByRole("list", { name: "Items" }).getByRole("listitem");
    await expect(items).toHaveText(["Desk lamp — $40.00", "Notebook — $8.00"]);
    await expect(page.locator("#co-shipping-line")).toHaveText(`Shipping (${label}): ${cost}`);
    await expect(page.locator("#co-total")).toHaveText(`Total: ${total}`);
  });
}

test("confirming shows the order number and lists the order, also after reload", async ({ page }) => {
  await fillAddress(page, address);
  await chooseMethod(page, "Express");
  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.locator("#co-step")).toHaveText("Order placed");
  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");
  const orders = page.getByRole("list", { name: "Your orders" }).getByRole("listitem");
  await expect(orders).toHaveText(["Order #1001 — $63.00 — London"]);

  await page.reload();
  await expect(orders).toHaveText(["Order #1001 — $63.00 — London"]);
});

test("going back keeps what the shopper typed and chosen method", async ({ page }) => {
  await fillAddress(page, address);
  await chooseMethod(page, "Express");

  await page.getByRole("button", { name: "Back" }).click();
  await expect(page.locator("#co-step")).toHaveText("Step 2 of 3");
  await expect(page.getByLabel("Express")).toBeChecked();

  await page.getByRole("button", { name: "Back" }).click();
  await expect(page.locator("#co-step")).toHaveText("Step 1 of 3");
  await expect(page.getByLabel("Full name")).toHaveValue(address.name);
  await expect(page.getByLabel("Street")).toHaveValue(address.street);
  await expect(page.getByLabel("City")).toHaveValue(address.city);
});

test("edited address from an earlier step is used for the order", async ({ page }) => {
  await fillAddress(page, address);
  await page.getByRole("button", { name: "Back" }).click();
  await page.getByLabel("City").fill("Paris");
  await page.getByRole("button", { name: "Next" }).click();
  await chooseMethod(page, "Standard");
  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveText([
    "Order #1001 — $53.00 — Paris",
  ]);
});

test("declined payment keeps the shopper on review and orders nothing", async ({ page }) => {
  await fillAddress(page, { ...address, city: "Failville" });
  await chooseMethod(page, "Standard");
  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.getByRole("alert")).toHaveText("Payment declined");
  await expect(page.locator("#co-step")).toHaveText("Step 3 of 3");
  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Thank you" })).toBeHidden();
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("list", { name: "Your orders" }).getByRole("listitem")).toHaveCount(0);
});

test("a declined payment does not consume the order number", async ({ page }) => {
  await fillAddress(page, { ...address, city: "Failville" });
  await chooseMethod(page, "Standard");
  await page.getByRole("button", { name: "Confirm order" }).click();
  await expect(page.getByRole("alert")).toHaveText("Payment declined");

  await page.getByRole("button", { name: "Back" }).click();
  await page.getByRole("button", { name: "Back" }).click();
  await page.getByLabel("City").fill("London");
  await page.getByRole("button", { name: "Next" }).click();
  await chooseMethod(page, "Standard");
  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");
});
