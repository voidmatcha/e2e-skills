import { expect, test } from "@playwright/test";

const summary = (page) => page.locator("#cp-summary");
const couponInput = (page) => page.getByLabel("Coupon code");
const applyButton = (page) => page.getByRole("button", { name: "Apply", exact: true });
const removeButton = (page) => page.getByRole("button", { name: "Remove", exact: true });
const alert = (page) => page.getByRole("alert");
const appliedCoupon = (page, code) => page.getByText(`Applied: ${code}`);

async function expectSummary(page, { discount, shipping, total }) {
  // JUSTIFIED: the order summary has an accessible label, but no reliable role in Playwright.
  await expect(summary(page)).toContainText(
    new RegExp(
      `Subtotal\\s*\\$80\\.00\\s+Discount\\s*-\\$${discount}\\s+Shipping\\s*\\$${shipping}\\s+Total\\s*\\$${total}`,
    ),
  );
}

async function applyCoupon(page, code) {
  const request = page.waitForRequest(
    (req) => req.method() === "POST" && new URL(req.url()).pathname === "/api/coupon",
  );
  await couponInput(page).fill(code);
  await applyButton(page).click();
  const couponRequest = await request;
  expect(couponRequest.postDataJSON()).toEqual({ code });
}

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Checkout", exact: true })).toBeVisible();
  await expectSummary(page, { discount: "0.00", shipping: "6.00", total: "86.00" });
});

test("applies SAVE10 and keeps it after reload", async ({ page }) => {
  await applyCoupon(page, "SAVE10");

  await expect(appliedCoupon(page, "SAVE10")).toBeVisible();
  await expectSummary(page, { discount: "8.00", shipping: "6.00", total: "78.00" });

  await page.reload();
  await expect(appliedCoupon(page, "SAVE10")).toBeVisible();
  await expectSummary(page, { discount: "8.00", shipping: "6.00", total: "78.00" });
});

test("replaces SAVE10 with FREESHIP", async ({ page }) => {
  await applyCoupon(page, "SAVE10");
  await expect(appliedCoupon(page, "SAVE10")).toBeVisible();

  await applyCoupon(page, "FREESHIP");

  await expect(appliedCoupon(page, "FREESHIP")).toBeVisible();
  await expectSummary(page, { discount: "0.00", shipping: "0.00", total: "80.00" });
});

test("shows expired coupon errors without changing the summary", async ({ page }) => {
  await applyCoupon(page, "EXPIRED1");

  await expect(alert(page)).toHaveText("That coupon has expired");
  await expectSummary(page, { discount: "0.00", shipping: "6.00", total: "86.00" });
});

test("shows unknown coupon errors without changing the summary", async ({ page }) => {
  await applyCoupon(page, "NOPE");

  await expect(alert(page)).toHaveText("Unknown coupon code");
  await expectSummary(page, { discount: "0.00", shipping: "6.00", total: "86.00" });
});

test("removes an applied coupon and restores the original summary", async ({ page }) => {
  await applyCoupon(page, "FREESHIP");
  await expect(appliedCoupon(page, "FREESHIP")).toBeVisible();

  const request = page.waitForRequest(
    (req) => req.method() === "DELETE" && new URL(req.url()).pathname === "/api/coupon",
  );
  await removeButton(page).click();
  await request;

  await expectSummary(page, { discount: "0.00", shipping: "6.00", total: "86.00" });
});
