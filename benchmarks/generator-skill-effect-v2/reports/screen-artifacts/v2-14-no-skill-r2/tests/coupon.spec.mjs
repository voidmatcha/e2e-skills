import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.locator("#cp-subtotal")).toHaveText("$80.00");
});

async function apply(page, code) {
  await page.getByLabel("Coupon code").fill(code);
  await page.getByRole("button", { name: "Apply" }).click();
}

async function expectSummary(page, { discount, shipping, total }) {
  await expect(page.locator("#cp-subtotal")).toHaveText("$80.00");
  await expect(page.locator("#cp-discount")).toHaveText(discount);
  await expect(page.locator("#cp-shipping")).toHaveText(shipping);
  await expect(page.locator("#cp-total")).toHaveText(total);
}

const original = { discount: "-$0.00", shipping: "$6.00", total: "$86.00" };

test("starts with the original summary and no coupon applied", async ({ page }) => {
  await expectSummary(page, original);
  await expect(page.locator("#cp-applied")).toBeHidden();
});

test("SAVE10 takes 10% off the subtotal", async ({ page }) => {
  await apply(page, "SAVE10");
  await expect(page.locator("#cp-applied")).toBeVisible();
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await expectSummary(page, { discount: "-$8.00", shipping: "$6.00", total: "$78.00" });
});

test("FREESHIP makes shipping free", async ({ page }) => {
  await apply(page, "FREESHIP");
  await expect(page.locator("#cp-applied-code")).toHaveText("FREESHIP");
  await expectSummary(page, { discount: "-$0.00", shipping: "$0.00", total: "$80.00" });
});

test("applying a second code replaces the first", async ({ page }) => {
  await apply(page, "SAVE10");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await apply(page, "FREESHIP");
  await expect(page.locator("#cp-applied-code")).toHaveText("FREESHIP");
  await expectSummary(page, { discount: "-$0.00", shipping: "$0.00", total: "$80.00" });

  await apply(page, "SAVE10");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await expectSummary(page, { discount: "-$8.00", shipping: "$6.00", total: "$78.00" });
});

test("an expired code is rejected and the summary is unchanged", async ({ page }) => {
  await apply(page, "EXPIRED1");
  await expect(page.getByRole("alert")).toHaveText("That coupon has expired");
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, original);
});

test("an unknown code is rejected and the summary is unchanged", async ({ page }) => {
  await apply(page, "NOPE");
  await expect(page.getByRole("alert")).toHaveText("Unknown coupon code");
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, original);
});

test("a rejected code leaves a previously applied coupon in place", async ({ page }) => {
  await apply(page, "SAVE10");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await apply(page, "EXPIRED1");
  await expect(page.getByRole("alert")).toHaveText("That coupon has expired");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await expectSummary(page, { discount: "-$8.00", shipping: "$6.00", total: "$78.00" });
});

test("Remove restores the original summary", async ({ page }) => {
  await apply(page, "SAVE10");
  await expect(page.locator("#cp-applied")).toBeVisible();
  await page.getByRole("button", { name: "Remove" }).click();
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, original);
});

test("the applied coupon survives a reload", async ({ page }) => {
  await apply(page, "SAVE10");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await page.reload();
  await expect(page.locator("#cp-applied")).toBeVisible();
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await expectSummary(page, { discount: "-$8.00", shipping: "$6.00", total: "$78.00" });
});
