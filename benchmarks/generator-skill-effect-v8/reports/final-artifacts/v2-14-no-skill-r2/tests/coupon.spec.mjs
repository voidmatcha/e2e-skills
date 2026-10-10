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

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

async function applyCoupon(page, code) {
  await page.getByLabel("Coupon code").fill(code);
  await page.getByRole("button", { name: "Apply" }).click();
}

async function expectSummary(page, summary) {
  await expect(page.locator("#cp-subtotal")).toHaveText(summary.subtotal);
  await expect(page.locator("#cp-discount")).toHaveText(summary.discount);
  await expect(page.locator("#cp-shipping")).toHaveText(summary.shipping);
  await expect(page.locator("#cp-total")).toHaveText(summary.total);
}

test("applies SAVE10 and keeps it after reload", async ({ page }) => {
  await page.goto("/");
  await expectSummary(page, originalSummary);

  await applyCoupon(page, "SAVE10");

  await expect(page.getByText("Applied: SAVE10")).toBeVisible();
  await expectSummary(page, save10Summary);

  await page.reload();

  await expect(page.getByText("Applied: SAVE10")).toBeVisible();
  await expectSummary(page, save10Summary);
});

test("applies FREESHIP", async ({ page }) => {
  await page.goto("/");

  await applyCoupon(page, "FREESHIP");

  await expect(page.getByText("Applied: FREESHIP")).toBeVisible();
  await expectSummary(page, freeShipSummary);
});

test("replaces the applied coupon when another valid code is applied", async ({ page }) => {
  await page.goto("/");

  await applyCoupon(page, "SAVE10");
  await expect(page.getByText("Applied: SAVE10")).toBeVisible();
  await expectSummary(page, save10Summary);

  await applyCoupon(page, "FREESHIP");

  await expect(page.getByText("Applied: FREESHIP")).toBeVisible();
  await expect(page.getByText("Applied: SAVE10")).toBeHidden();
  await expectSummary(page, freeShipSummary);
});

test("rejects expired and unknown coupon codes without changing the summary", async ({ page }) => {
  await page.goto("/");
  await expectSummary(page, originalSummary);

  await applyCoupon(page, "EXPIRED1");

  await expect(page.getByRole("alert")).toHaveText("That coupon has expired");
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, originalSummary);

  await applyCoupon(page, "NOTACODE");

  await expect(page.getByRole("alert")).toHaveText("Unknown coupon code");
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, originalSummary);
});

test("removes the applied coupon and restores the original summary", async ({ page }) => {
  await page.goto("/");
  await applyCoupon(page, "SAVE10");
  await expectSummary(page, save10Summary);

  await page.getByRole("button", { name: "Remove" }).click();

  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, originalSummary);
});
