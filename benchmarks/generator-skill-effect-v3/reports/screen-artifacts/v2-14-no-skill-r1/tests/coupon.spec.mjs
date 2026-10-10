import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  // The applied coupon lives on the server, so start every test from a clean slate.
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.locator("#cp-total")).toHaveText("$86.00");
});

const apply = async (page, code) => {
  await page.getByLabel("Coupon code").fill(code);
  await page.getByRole("button", { name: "Apply" }).click();
};

const expectSummary = async (page, { subtotal, discount, shipping, total }) => {
  await expect(page.locator("#cp-subtotal")).toHaveText(subtotal);
  await expect(page.locator("#cp-discount")).toHaveText(discount);
  await expect(page.locator("#cp-shipping")).toHaveText(shipping);
  await expect(page.locator("#cp-total")).toHaveText(total);
};

const original = { subtotal: "$80.00", discount: "-$0.00", shipping: "$6.00", total: "$86.00" };
const save10 = { subtotal: "$80.00", discount: "-$8.00", shipping: "$6.00", total: "$78.00" };
const freeship = { subtotal: "$80.00", discount: "-$0.00", shipping: "$0.00", total: "$80.00" };

test("shows the two-item cart with the original summary", async ({ page }) => {
  await expect(page.getByRole("list", { name: "Items" }).getByRole("listitem")).toHaveCount(2);
  await expectSummary(page, original);
  await expect(page.locator("#cp-applied")).toBeHidden();
});

test("SAVE10 takes 10% off the subtotal", async ({ page }) => {
  await apply(page, "SAVE10");
  await expect(page.locator("#cp-applied")).toBeVisible();
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await expectSummary(page, save10);
});

test("FREESHIP makes shipping free", async ({ page }) => {
  await apply(page, "FREESHIP");
  await expect(page.locator("#cp-applied-code")).toHaveText("FREESHIP");
  await expectSummary(page, freeship);
});

test("applying a second code replaces the first", async ({ page }) => {
  await apply(page, "SAVE10");
  await expectSummary(page, save10);
  await apply(page, "FREESHIP");
  await expect(page.locator("#cp-applied-code")).toHaveText("FREESHIP");
  await expectSummary(page, freeship);
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
  await expectSummary(page, save10);
  await apply(page, "EXPIRED1");
  await expect(page.getByRole("alert")).toHaveText("That coupon has expired");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await expectSummary(page, save10);
});

test("Remove takes the coupon off and restores the summary", async ({ page }) => {
  await apply(page, "SAVE10");
  await expectSummary(page, save10);
  await page.getByRole("button", { name: "Remove" }).click();
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, original);
});

test("the applied coupon survives a reload", async ({ page }) => {
  await apply(page, "SAVE10");
  await expectSummary(page, save10);
  await page.reload();
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await expectSummary(page, save10);
});

test("a removed coupon stays removed after a reload", async ({ page }) => {
  await apply(page, "FREESHIP");
  await expectSummary(page, freeship);
  await page.getByRole("button", { name: "Remove" }).click();
  await expectSummary(page, original);
  await page.reload();
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, original);
});
