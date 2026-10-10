import { expect, test } from "@playwright/test";

const originalSummary = {
  discount: "-$0.00",
  shipping: "$6.00",
  total: "$86.00",
};

const save10Summary = {
  discount: "-$8.00",
  shipping: "$6.00",
  total: "$78.00",
};

const freeShipSummary = {
  discount: "-$0.00",
  shipping: "$0.00",
  total: "$80.00",
};

function orderSummary(page) {
  return page.getByLabel("Order summary");
}

function escapeRegex(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function expectOrderSummary(page, expected) {
  await expect(orderSummary(page)).toHaveText(
    new RegExp(
      `Subtotal\\s*\\$80\\.00\\s*Discount\\s*${escapeRegex(expected.discount)}\\s*Shipping\\s*${escapeRegex(expected.shipping)}\\s*Total\\s*${escapeRegex(expected.total)}`,
    ),
  );
}

async function applyCoupon(page, code) {
  await page.getByRole("textbox", { name: /^Coupon code$/ }).fill(code);
  const couponRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/coupon",
  );
  await page.getByRole("button", { name: /^Apply$/ }).click();
  const request = await couponRequest;
  expect(request.postDataJSON()).toEqual({ code });
}

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /^Checkout$/ })).toBeVisible();
  await expectOrderSummary(page, originalSummary);
});

test("applies valid coupons, replaces the active coupon, persists across reloads, and removes it", async ({
  page,
}) => {
  await applyCoupon(page, "SAVE10");
  await expect(page.getByText("Applied: SAVE10")).toBeVisible();
  await expectOrderSummary(page, save10Summary);

  await applyCoupon(page, "FREESHIP");
  await expect(page.getByText("Applied: FREESHIP")).toBeVisible();
  await expect(page.getByText(/^Applied:/)).toHaveText("Applied: FREESHIP Remove");
  await expectOrderSummary(page, freeShipSummary);

  await page.reload();
  await expect(page.getByText("Applied: FREESHIP")).toBeVisible();
  await expectOrderSummary(page, freeShipSummary);

  const removeRequest = page.waitForRequest(
    (request) =>
      request.method() === "DELETE" &&
      new URL(request.url()).pathname === "/api/coupon",
  );
  await page.getByRole("button", { name: /^Remove$/ }).click();
  await removeRequest;
  await expectOrderSummary(page, originalSummary);
});

test("shows coupon errors without changing the order summary", async ({ page }) => {
  await applyCoupon(page, "EXPIRED1");
  await expect(page.getByRole("alert")).toHaveText("That coupon has expired");
  await expectOrderSummary(page, originalSummary);
  await page.reload();
  await expectOrderSummary(page, originalSummary);

  await applyCoupon(page, "NO_SUCH_CODE");
  await expect(page.getByRole("alert")).toHaveText("Unknown coupon code");
  await expectOrderSummary(page, originalSummary);
  await page.reload();
  await expectOrderSummary(page, originalSummary);
});
