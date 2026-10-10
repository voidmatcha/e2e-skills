import { expect, test } from "@playwright/test";

const originalSummary = {
  subtotal: "$80.00",
  discount: "-$0.00",
  shipping: "$6.00",
  total: "$86.00",
};

async function expectSummary(page, { subtotal, discount, shipping, total }) {
  await expect(page.locator("#cp-subtotal")).toHaveText(subtotal);
  await expect(page.locator("#cp-discount")).toHaveText(discount);
  await expect(page.locator("#cp-shipping")).toHaveText(shipping);
  await expect(page.locator("#cp-total")).toHaveText(total);
}

async function applyCoupon(page, code) {
  await page.getByLabel("Coupon code").fill(code);
  await page.getByRole("button", { name: "Apply" }).click();
}

test.beforeEach(async ({ request, page }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("applies SAVE10 for 10 percent off the subtotal", async ({ page }) => {
  await expectSummary(page, originalSummary);

  await applyCoupon(page, "SAVE10");

  await expect(page.locator("#cp-applied")).toBeVisible();
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await expectSummary(page, {
    subtotal: "$80.00",
    discount: "-$8.00",
    shipping: "$6.00",
    total: "$78.00",
  });
});

test("applies FREESHIP for free shipping", async ({ page }) => {
  await applyCoupon(page, "FREESHIP");

  await expect(page.locator("#cp-applied")).toBeVisible();
  await expect(page.locator("#cp-applied-code")).toHaveText("FREESHIP");
  await expectSummary(page, {
    subtotal: "$80.00",
    discount: "-$0.00",
    shipping: "$0.00",
    total: "$80.00",
  });
});

test("replaces the applied coupon when another valid code is applied", async ({ page }) => {
  await applyCoupon(page, "SAVE10");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");

  await applyCoupon(page, "FREESHIP");

  await expect(page.locator("#cp-applied-code")).toHaveText("FREESHIP");
  await expectSummary(page, {
    subtotal: "$80.00",
    discount: "-$0.00",
    shipping: "$0.00",
    total: "$80.00",
  });
});

test("rejects expired and unknown coupons without changing the summary", async ({ page }) => {
  await expectSummary(page, originalSummary);

  await applyCoupon(page, "EXPIRED1");
  await expect(page.getByRole("alert")).toHaveText("That coupon has expired");
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, originalSummary);

  await applyCoupon(page, "NOPE");
  await expect(page.getByRole("alert")).toHaveText("Unknown coupon code");
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, originalSummary);
});

test("removes the applied coupon and restores the original summary", async ({ page }) => {
  await applyCoupon(page, "SAVE10");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");

  await page.getByRole("button", { name: "Remove" }).click();

  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, originalSummary);
});

test("keeps the applied coupon after reload", async ({ page }) => {
  await applyCoupon(page, "SAVE10");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");

  await page.reload();

  await expect(page.locator("#cp-applied")).toBeVisible();
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await expectSummary(page, {
    subtotal: "$80.00",
    discount: "-$8.00",
    shipping: "$6.00",
    total: "$78.00",
  });
});
