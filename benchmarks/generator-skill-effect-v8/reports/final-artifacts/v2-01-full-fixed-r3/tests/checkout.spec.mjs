import { expect, test } from "@playwright/test";

const address = {
  name: "Ada Lovelace",
  street: "1 Algorithm Ave",
  city: "London",
};

async function resetOrders(request) {
  await request.post("/api/reset");
}

async function fillAddress(page, { name, street, city }) {
  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Street").fill(street);
  await page.getByLabel("City").fill(city);
}

async function continueToReview(page, shippingMethod = "Standard ($5.00)") {
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("radio", { name: shippingMethod, exact: true }).check();
  await page.getByRole("button", { name: "Next", exact: true }).click();
}

test.beforeEach(async ({ page, request }) => {
  await resetOrders(request);
  await page.goto("/");
});

test("confirms an order and keeps it under Your orders after reload", async ({ page }) => {
  await fillAddress(page, address);
  await continueToReview(page, "Express ($15.00)");

  await expect(page.getByRole("list", { name: "Items", exact: true }).getByRole("listitem")).toHaveText([
    "Desk lamp — $40.00",
    "Notebook — $8.00",
  ]);
  await expect(page.getByText("Shipping (Express): $15.00")).toBeVisible();
  await expect(page.getByText("Total: $63.00")).toBeVisible();

  const orderRequest = page.waitForRequest((request) => {
    return request.method() === "POST" && new URL(request.url()).pathname === "/api/orders";
  });
  const orderResponse = page.waitForResponse((response) => {
    return response.request().method() === "POST" && new URL(response.url()).pathname === "/api/orders";
  });
  await page.getByRole("button", { name: "Confirm order", exact: true }).click();
  const requestBody = JSON.parse((await orderRequest).postData() ?? "{}");
  expect(requestBody).toMatchObject({ address, method: "express" });
  expect((await orderResponse).status()).toBe(201);

  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");
  await page.reload();
  await expect(page.getByRole("list", { name: "Your orders", exact: true })).toContainText(
    "Order #1001 — $63.00 — London",
  );
});

test("keeps the shipping address when returning from the method step", async ({ page }) => {
  await fillAddress(page, {
    name: "Grace Hopper",
    street: "2 Compiler Rd",
    city: "Arlington",
  });

  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Back", exact: true }).click();

  await expect(page.getByLabel("Full name")).toHaveValue("Grace Hopper");
  await expect(page.getByLabel("Street")).toHaveValue("2 Compiler Rd");
  await expect(page.getByLabel("City")).toHaveValue("Arlington");
});

test("shows Payment declined and does not add an order", async ({ page, request }) => {
  await fillAddress(page, {
    ...address,
    city: "Failville",
  });
  await continueToReview(page);

  const orderResponse = page.waitForResponse((response) => {
    return response.request().method() === "POST" && new URL(response.url()).pathname === "/api/orders";
  });
  await page.getByRole("button", { name: "Confirm order", exact: true }).click();
  expect((await orderResponse).status()).toBe(402);

  await expect(page.getByRole("heading", { name: "Review", exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveText("Payment declined");
  await page.reload();
  const storedOrders = await request.get("/api/orders");
  expect(await storedOrders.json()).toEqual([]);
  await expect(page.getByRole("list", { name: "Your orders", exact: true }).getByRole("listitem")).toHaveCount(0);
});
