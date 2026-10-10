import { expect, test } from "@playwright/test";

// Coupon state lives on the server, so start every test from a clean slate.
test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBe(true);
  await page.goto("/");
  await expectSummary(page, { subtotal: "$80.00", discount: "-$0.00", shipping: "$6.00", total: "$86.00" });
});

async function expectSummary(page, { subtotal, discount, shipping, total }) {
  const summary = page.getByLabel("Order summary");
  await expect(summary.locator("#cp-subtotal")).toHaveText(subtotal);
  await expect(summary.locator("#cp-discount")).toHaveText(discount);
  await expect(summary.locator("#cp-shipping")).toHaveText(shipping);
  await expect(summary.locator("#cp-total")).toHaveText(total);
}

async function applyCoupon(page, code) {
  await page.getByLabel("Coupon code").fill(code);
  await page.getByRole("button", { name: "Apply" }).click();
}

const applied = (page) => page.locator("#cp-applied");
const SAVE10 = { subtotal: "$80.00", discount: "-$8.00", shipping: "$6.00", total: "$78.00" };
const FREESHIP = { subtotal: "$80.00", discount: "-$0.00", shipping: "$0.00", total: "$80.00" };
const ORIGINAL = { subtotal: "$80.00", discount: "-$0.00", shipping: "$6.00", total: "$86.00" };

test("lists the two cart items", async ({ page }) => {
  await expect(page.getByLabel("Items").getByRole("listitem")).toHaveCount(2);
  await expect(applied(page)).toBeHidden();
});

test("SAVE10 takes 10% off the subtotal", async ({ page }) => {
  await applyCoupon(page, "SAVE10");
  await expect(applied(page)).toBeVisible();
  await expect(applied(page)).toContainText("SAVE10");
  await expectSummary(page, SAVE10);
});

test("FREESHIP makes shipping free", async ({ page }) => {
  await applyCoupon(page, "FREESHIP");
  await expect(applied(page)).toContainText("FREESHIP");
  await expectSummary(page, FREESHIP);
});

test("applying a second coupon replaces the first", async ({ page }) => {
  await applyCoupon(page, "SAVE10");
  await expectSummary(page, SAVE10);
  await applyCoupon(page, "FREESHIP");
  await expect(applied(page)).toContainText("FREESHIP");
  await expect(applied(page)).not.toContainText("SAVE10");
  await expectSummary(page, FREESHIP);
});

test("an expired coupon is rejected and the summary is unchanged", async ({ page }) => {
  await applyCoupon(page, "EXPIRED1");
  await expect(page.getByRole("alert")).toHaveText("That coupon has expired");
  await expect(applied(page)).toBeHidden();
  await expectSummary(page, ORIGINAL);
});

test("an unknown coupon is rejected and the summary is unchanged", async ({ page }) => {
  await applyCoupon(page, "NOPE");
  await expect(page.getByRole("alert")).toHaveText("Unknown coupon code");
  await expect(applied(page)).toBeHidden();
  await expectSummary(page, ORIGINAL);
});

test("a rejected code leaves a previously applied coupon in place", async ({ page }) => {
  await applyCoupon(page, "SAVE10");
  await expectSummary(page, SAVE10);
  await applyCoupon(page, "EXPIRED1");
  await expect(page.getByRole("alert")).toHaveText("That coupon has expired");
  await expect(applied(page)).toContainText("SAVE10");
  await expectSummary(page, SAVE10);
});

test("remove takes the coupon off and restores the summary", async ({ page }) => {
  await applyCoupon(page, "SAVE10");
  await expectSummary(page, SAVE10);
  await applied(page).getByRole("button", { name: "Remove" }).click();
  await expect(applied(page)).toBeHidden();
  await expectSummary(page, ORIGINAL);
});

test("the applied coupon survives a reload", async ({ page }) => {
  await applyCoupon(page, "SAVE10");
  await expectSummary(page, SAVE10);
  await page.reload();
  await expect(applied(page)).toContainText("SAVE10");
  await expectSummary(page, SAVE10);
});

test("a removed coupon stays removed after a reload", async ({ page }) => {
  await applyCoupon(page, "FREESHIP");
  await applied(page).getByRole("button", { name: "Remove" }).click();
  await page.reload();
  await expect(applied(page)).toBeHidden();
  await expectSummary(page, ORIGINAL);
});
