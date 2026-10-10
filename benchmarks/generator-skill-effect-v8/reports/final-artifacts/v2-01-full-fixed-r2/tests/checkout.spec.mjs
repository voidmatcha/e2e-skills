import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("completes checkout and keeps the order after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Full name").fill("Riley Chen");
  await page.getByLabel("Street").fill("12 Market Street");
  await page.getByLabel("City").fill("Springfield");
  await page.getByRole("button", { name: "Next", exact: true }).click();

  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(page.getByLabel("Full name")).toHaveValue("Riley Chen");
  await expect(page.getByLabel("Street")).toHaveValue("12 Market Street");
  await expect(page.getByLabel("City")).toHaveValue("Springfield");

  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByLabel("Express ($15.00)").check();
  await page.getByRole("button", { name: "Next", exact: true }).click();

  await expect(page.getByRole("list", { name: "Items", exact: true }).getByRole("listitem")).toContainText([
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

  const request = await orderRequest;
  expect(request.postDataJSON()).toEqual({
    address: {
      name: "Riley Chen",
      street: "12 Market Street",
      city: "Springfield",
    },
    method: "express",
  });
  const response = await orderResponse;
  expect(response.status()).toBe(201);

  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");
  await expect(page.getByRole("list", { name: "Your orders", exact: true })).toContainText(
    "Order #1001 — $63.00 — Springfield",
  );

  await page.reload();
  await expect(page.getByRole("list", { name: "Your orders", exact: true })).toContainText(
    "Order #1001 — $63.00 — Springfield",
  );
});

test("keeps the shopper on review when payment is declined", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Full name").fill("Morgan Park");
  await page.getByLabel("Street").fill("404 Test Lane");
  await page.getByLabel("City").fill("Failville");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Review", exact: true })).toBeVisible();
  await expect(page.getByText("Shipping (Standard): $5.00")).toBeVisible();
  await expect(page.getByText("Total: $53.00")).toBeVisible();

  const orderRequest = page.waitForRequest((request) => {
    return request.method() === "POST" && new URL(request.url()).pathname === "/api/orders";
  });
  const orderResponse = page.waitForResponse((response) => {
    return response.request().method() === "POST" && new URL(response.url()).pathname === "/api/orders";
  });
  await page.getByRole("button", { name: "Confirm order", exact: true }).click();

  const request = await orderRequest;
  expect(request.postDataJSON()).toEqual({
    address: {
      name: "Morgan Park",
      street: "404 Test Lane",
      city: "Failville",
    },
    method: "standard",
  });
  const response = await orderResponse;
  expect(response.status()).toBe(402);

  await expect(page.getByRole("alert")).toHaveText("Payment declined");
  await expect(page.getByRole("heading", { name: "Review", exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("list", { name: "Your orders", exact: true })).toBeEmpty();
});
