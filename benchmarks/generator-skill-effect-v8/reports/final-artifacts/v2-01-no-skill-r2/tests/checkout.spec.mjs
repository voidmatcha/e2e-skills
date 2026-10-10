import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

async function fillAddress(page, { name = "Ada Lovelace", street = "12 Algorithm Lane", city = "London" } = {}) {
  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Street").fill(street);
  await page.getByLabel("City").fill(city);
}

async function continueFromAddress(page) {
  await page.getByRole("button", { name: "Next" }).click();
}

async function expectReview(page, { shipping, total }) {
  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Items" }).locator("li")).toHaveText([
    "Desk lamp — $40.00",
    "Notebook — $8.00",
  ]);
  await expect(page.locator("#co-shipping-line")).toHaveText(shipping);
  await expect(page.locator("#co-total")).toHaveText(total);
}

test("shopper completes checkout and sees the order after reload", async ({ page }) => {
  await page.goto("/");

  await fillAddress(page, { name: "Grace Hopper", street: "7 Compiler Court", city: "Arlington" });
  await continueFromAddress(page);
  await page.getByLabel("Express ($15.00)").check();
  await page.getByRole("button", { name: "Next" }).click();

  await expectReview(page, {
    shipping: "Shipping (Express): $15.00",
    total: "Total: $63.00",
  });

  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.getByRole("heading", { name: "Thank you" })).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");
  await expect(page.getByRole("list", { name: "Your orders" })).toContainText("Order #1001 — $63.00 — Arlington");

  await page.reload();

  await expect(page.getByRole("list", { name: "Your orders" })).toContainText("Order #1001 — $63.00 — Arlington");
});

test("going back to shipping keeps the entered address", async ({ page }) => {
  await page.goto("/");

  await fillAddress(page, { name: "Katherine Johnson", street: "101 Orbit Road", city: "Hampton" });
  await continueFromAddress(page);

  await expect(page.getByRole("heading", { name: "Shipping method" })).toBeVisible();
  await page.getByRole("button", { name: "Back" }).click();

  await expect(page.getByRole("heading", { name: "Shipping address" })).toBeVisible();
  await expect(page.getByLabel("Full name")).toHaveValue("Katherine Johnson");
  await expect(page.getByLabel("Street")).toHaveValue("101 Orbit Road");
  await expect(page.getByLabel("City")).toHaveValue("Hampton");
});

test("declined payment stays on review and does not create an order", async ({ page }) => {
  await page.goto("/");

  await fillAddress(page, { city: "Failville" });
  await continueFromAddress(page);
  await page.getByRole("button", { name: "Next" }).click();

  await expectReview(page, {
    shipping: "Shipping (Standard): $5.00",
    total: "Total: $53.00",
  });

  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveText("Payment declined");
  await expect(page.getByRole("list", { name: "Your orders" }).locator("li")).toHaveCount(0);
});
