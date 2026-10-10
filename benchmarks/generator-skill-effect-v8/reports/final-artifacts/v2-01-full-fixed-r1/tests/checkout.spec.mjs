import { expect, test } from "@playwright/test";

const address = {
  name: "Ada Lovelace",
  street: "12 Analytical Engine Way",
  city: "London",
};

async function resetOrders(request) {
  const response = await request.post("/api/reset");
  expect(response.status()).toBe(200);
}

async function fillAddress(page, details) {
  await page.getByLabel("Full name").fill(details.name);
  await page.getByLabel("Street").fill(details.street);
  await page.getByLabel("City").fill(details.city);
  await page.getByRole("button", { name: "Next" }).click();
}

async function expectReviewTotals(page, method, shipping, total) {
  const items = page.getByRole("list", { name: "Items" }).getByRole("listitem");
  await expect(items).toHaveCount(2);
  await expect(items.filter({ hasText: "Desk lamp" })).toContainText("$40.00");
  await expect(items.filter({ hasText: "Notebook" })).toContainText("$8.00");
  await expect(page.getByText(`Shipping (${method}): ${shipping}`)).toBeVisible();
  await expect(page.getByText(`Total: ${total}`)).toBeVisible();
}

function orderWrite(page) {
  const isOrderWrite = (requestOrResponse) => {
    const request = "request" in requestOrResponse ? requestOrResponse.request() : requestOrResponse;
    return request.method() === "POST" && new URL(request.url()).pathname === "/api/orders";
  };

  return {
    request: page.waitForRequest(isOrderWrite),
    response: page.waitForResponse(isOrderWrite),
  };
}

test.beforeEach(async ({ request }) => {
  await resetOrders(request);
});

test("places an order and keeps it under Your orders after reload", async ({ page }) => {
  await page.goto("/");

  await fillAddress(page, address);
  await page.getByLabel("Express ($15.00)").check();
  await page.getByRole("button", { name: "Next" }).click();
  await expectReviewTotals(page, "Express", "$15.00", "$63.00");

  await page.getByRole("button", { name: "Back" }).click();
  await page.getByRole("button", { name: "Back" }).click();
  await expect(page.getByLabel("Full name")).toHaveValue(address.name);
  await expect(page.getByLabel("Street")).toHaveValue(address.street);
  await expect(page.getByLabel("City")).toHaveValue(address.city);

  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();

  const write = orderWrite(page);
  await page.getByRole("button", { name: "Confirm order" }).click();
  const [orderRequest, orderResponse] = await Promise.all([write.request, write.response]);

  expect(orderRequest.postDataJSON()).toEqual({ address, method: "express" });
  expect(orderResponse.status()).toBe(201);
  await expect(page.getByRole("status")).toHaveText(/Order #\d+ confirmed/);

  const orderNumber = (await page.getByRole("status").textContent()).match(/#(\d+)/)[1];
  const orderSummary = new RegExp(`Order #${orderNumber}.+\\$63\\.00.+London`);
  await expect(page.getByRole("list", { name: "Your orders" })).toContainText(orderSummary);

  await page.reload();
  await expect(page.getByRole("list", { name: "Your orders" })).toContainText(orderSummary);
});

test("stays on review and stores nothing when payment is declined", async ({ page, request }) => {
  const declinedAddress = { ...address, city: "Failville" };
  await page.goto("/");

  await fillAddress(page, declinedAddress);
  await page.getByRole("button", { name: "Next" }).click();
  await expectReviewTotals(page, "Standard", "$5.00", "$53.00");

  const write = orderWrite(page);
  await page.getByRole("button", { name: "Confirm order" }).click();
  const [orderRequest, orderResponse] = await Promise.all([write.request, write.response]);

  expect(orderRequest.postDataJSON()).toEqual({ address: declinedAddress, method: "standard" });
  expect(orderResponse.status()).toBe(402);
  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveText("Payment declined");

  await page.reload();
  await expect(page.getByRole("heading", { name: "Your orders" })).toBeVisible();
  const orders = await (await request.get("/api/orders")).json();
  expect(orders).toEqual([]);
});
