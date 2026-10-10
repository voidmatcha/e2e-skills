import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.locator("#cp-subtotal")).toHaveText("$80.00");
});

const apply = async (page, code) => {
  await page.getByLabel("Coupon code").fill(code);
  await page.getByRole("button", { name: "Apply" }).click();
};

const expectSummary = async (page, { discount, shipping, total }) => {
  const summary = page.getByRole("term").filter({ hasText: /^Subtotal$/ });
  await expect(summary).toBeVisible();
  await expect(page.locator("#cp-subtotal")).toHaveText("$80.00");
  await expect(page.locator("#cp-discount")).toHaveText(discount);
  await expect(page.locator("#cp-shipping")).toHaveText(shipping);
  await expect(page.locator("#cp-total")).toHaveText(total);
};

const original = { discount: "-$0.00", shipping: "$6.00", total: "$86.00" };

test("shows the original summary with no coupon", async ({ page }) => {
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

test("applying a second coupon replaces the first", async ({ page }) => {
  await apply(page, "SAVE10");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await apply(page, "FREESHIP");
  await expect(page.locator("#cp-applied-code")).toHaveText("FREESHIP");
  await expectSummary(page, { discount: "-$0.00", shipping: "$0.00", total: "$80.00" });
});

test("an expired coupon is rejected and leaves the summary unchanged", async ({ page }) => {
  await apply(page, "EXPIRED1");
  await expect(page.getByRole("alert")).toHaveText("That coupon has expired");
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, original);
});

test("an unknown coupon is rejected and leaves the summary unchanged", async ({ page }) => {
  await apply(page, "NOPE");
  await expect(page.getByRole("alert")).toHaveText("Unknown coupon code");
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, original);
});

test("a rejected code keeps a previously applied coupon", async ({ page }) => {
  await apply(page, "SAVE10");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await apply(page, "EXPIRED1");
  await expect(page.getByRole("alert")).toHaveText("That coupon has expired");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await expectSummary(page, { discount: "-$8.00", shipping: "$6.00", total: "$78.00" });
});

test("remove takes the coupon off and restores the summary", async ({ page }) => {
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
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await expectSummary(page, { discount: "-$8.00", shipping: "$6.00", total: "$78.00" });
});
