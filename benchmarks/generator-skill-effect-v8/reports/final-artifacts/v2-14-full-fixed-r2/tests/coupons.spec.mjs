import { expect, test } from "@playwright/test";

const originalSummary = {
  subtotal: "$80.00",
  discount: "-$0.00",
  shipping: "$6.00",
  total: "$86.00",
};

const save10Summary = {
  subtotal: "$80.00",
  discount: "-$8.00",
  shipping: "$6.00",
  total: "$78.00",
};

const freeShipSummary = {
  subtotal: "$80.00",
  discount: "-$0.00",
  shipping: "$0.00",
  total: "$80.00",
};

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Checkout", exact: true })).toBeVisible();
  await expectSummary(page, originalSummary);
});

test("applies SAVE10 and keeps it applied after reload", async ({ page }) => {
  await applyCoupon(page, "SAVE10", 200);

  await expect(page.getByText("Applied: SAVE10")).toBeVisible();
  await expectSummary(page, save10Summary);

  await page.reload();
  await expect(page.getByText("Applied: SAVE10")).toBeVisible();
  await expectSummary(page, save10Summary);
});

test("replaces SAVE10 when FREESHIP is applied", async ({ page }) => {
  await applyCoupon(page, "SAVE10", 200);
  await expect(page.getByText("Applied: SAVE10")).toBeVisible();

  await applyCoupon(page, "FREESHIP", 200);

  await expect(page.getByText("Applied: FREESHIP")).toBeVisible();
  await expect(page.getByText("Applied: SAVE10")).toBeHidden();
  await expectSummary(page, freeShipSummary);
});

test("shows errors for rejected coupons without changing the summary", async ({ page }) => {
  await applyRejectedCoupon(page, "EXPIRED1", 410, "That coupon has expired");
  await expectSummary(page, originalSummary);

  await applyRejectedCoupon(page, "NOTREAL", 404, "Unknown coupon code");
  await expectSummary(page, originalSummary);
});

test("removes the applied coupon and restores the original summary", async ({ page }) => {
  await applyCoupon(page, "FREESHIP", 200);
  await expect(page.getByText("Applied: FREESHIP")).toBeVisible();

  const removed = page.waitForResponse(
    (response) => response.url().endsWith("/api/coupon") && response.request().method() === "DELETE",
  );
  await page.getByRole("button", { name: "Remove", exact: true }).click();
  expect((await removed).status()).toBe(200);

  await expect(page.getByText("Applied: FREESHIP")).toBeHidden();
  await expectSummary(page, originalSummary);
});

async function applyCoupon(page, code, status) {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/coupon") &&
      response.request().method() === "POST" &&
      response.request().postDataJSON().code === code,
  );

  await page.getByLabel("Coupon code").fill(code);
  await page.getByRole("button", { name: "Apply", exact: true }).click();

  const response = await responsePromise;
  expect(response.status()).toBe(status);
}

async function applyRejectedCoupon(page, code, status, message) {
  await applyCoupon(page, code, status);
  await expect(page.getByRole("alert")).toHaveText(message);
}

async function expectSummary(page, { subtotal, discount, shipping, total }) {
  const summary = page.locator('[aria-label="Order summary"]');

  await expect(summary).toContainText(`Subtotal${subtotal}`);
  await expect(summary).toContainText(`Discount${discount}`);
  await expect(summary).toContainText(`Shipping${shipping}`);
  await expect(summary).toContainText(`Total${total}`);
}
