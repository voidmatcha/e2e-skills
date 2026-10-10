import { expect, test } from "@playwright/test";

const originalSummary = {
  subtotal: "$80.00",
  discount: "-$0.00",
  shipping: "$6.00",
  total: "$86.00",
};

const summary = (page) => ({
  subtotal: page.locator("#cp-subtotal"),
  discount: page.locator("#cp-discount"),
  shipping: page.locator("#cp-shipping"),
  total: page.locator("#cp-total"),
});

const expectSummary = async (page, expected) => {
  const fields = summary(page);
  await expect(fields.subtotal).toHaveText(expected.subtotal);
  await expect(fields.discount).toHaveText(expected.discount);
  await expect(fields.shipping).toHaveText(expected.shipping);
  await expect(fields.total).toHaveText(expected.total);
};

const applyCoupon = async (page, code) => {
  await page.getByLabel("Coupon code").fill(code);
  await Promise.all([
    page.waitForResponse((response) => response.url().endsWith("/api/coupon")),
    page.getByRole("button", { name: "Apply" }).click(),
  ]);
};

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("applies SAVE10 to discount the subtotal", async ({ page }) => {
  await page.goto("/");
  await applyCoupon(page, "SAVE10");

  await expect(page.locator("#cp-applied")).toContainText("Applied: SAVE10");
  await expectSummary(page, {
    subtotal: "$80.00",
    discount: "-$8.00",
    shipping: "$6.00",
    total: "$78.00",
  });
});

test("applies FREESHIP to remove shipping", async ({ page }) => {
  await page.goto("/");
  await applyCoupon(page, "FREESHIP");

  await expect(page.locator("#cp-applied")).toContainText("Applied: FREESHIP");
  await expectSummary(page, {
    subtotal: "$80.00",
    discount: "-$0.00",
    shipping: "$0.00",
    total: "$80.00",
  });
});

test("replaces the current coupon when a second code is applied", async ({ page }) => {
  await page.goto("/");
  await applyCoupon(page, "SAVE10");
  await applyCoupon(page, "FREESHIP");

  await expect(page.locator("#cp-applied")).toContainText("Applied: FREESHIP");
  await expectSummary(page, {
    subtotal: "$80.00",
    discount: "-$0.00",
    shipping: "$0.00",
    total: "$80.00",
  });
});

test("keeps the summary unchanged for invalid coupon codes", async ({ page }) => {
  await page.goto("/");
  await expectSummary(page, originalSummary);

  await applyCoupon(page, "EXPIRED1");
  await expect(page.getByRole("alert")).toHaveText("That coupon has expired");
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, originalSummary);

  await applyCoupon(page, "NOTREAL");
  await expect(page.getByRole("alert")).toHaveText("Unknown coupon code");
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, originalSummary);
});

test("removes the applied coupon and restores the original summary", async ({ page }) => {
  await page.goto("/");
  await applyCoupon(page, "SAVE10");
  await page.getByRole("button", { name: "Remove" }).click();

  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, originalSummary);
});

test("keeps the applied coupon after reload", async ({ page }) => {
  await page.goto("/");
  await applyCoupon(page, "SAVE10");

  await page.reload();

  await expect(page.locator("#cp-applied")).toContainText("Applied: SAVE10");
  await expectSummary(page, {
    subtotal: "$80.00",
    discount: "-$8.00",
    shipping: "$6.00",
    total: "$78.00",
  });
});
