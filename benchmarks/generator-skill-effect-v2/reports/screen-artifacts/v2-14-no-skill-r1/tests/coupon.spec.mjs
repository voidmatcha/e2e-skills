import { expect, test } from "@playwright/test";

const ORIGINAL = { subtotal: "$80.00", discount: "-$0.00", shipping: "$6.00", total: "$86.00" };

async function expectSummary(page, expected) {
  await expect(page.locator("#cp-subtotal")).toHaveText(expected.subtotal);
  await expect(page.locator("#cp-discount")).toHaveText(expected.discount);
  await expect(page.locator("#cp-shipping")).toHaveText(expected.shipping);
  await expect(page.locator("#cp-total")).toHaveText(expected.total);
}

async function apply(page, code) {
  await page.getByLabel("Coupon code").fill(code);
  await page.getByRole("button", { name: "Apply" }).click();
}

test.beforeEach(async ({ page, request }) => {
  // The app keeps the coupon in server memory, so start every test clean.
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expectSummary(page, ORIGINAL);
});

test("shows the two-item cart with the original summary and no coupon", async ({ page }) => {
  await expect(page.getByRole("list", { name: "Items" }).getByRole("listitem")).toHaveCount(2);
  await expect(page.locator("#cp-applied")).toBeHidden();
});

test("SAVE10 takes 10% off the subtotal", async ({ page }) => {
  await apply(page, "SAVE10");
  await expect(page.locator("#cp-applied")).toBeVisible();
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await expectSummary(page, { subtotal: "$80.00", discount: "-$8.00", shipping: "$6.00", total: "$78.00" });
});

test("FREESHIP makes shipping free", async ({ page }) => {
  await apply(page, "FREESHIP");
  await expect(page.locator("#cp-applied-code")).toHaveText("FREESHIP");
  await expectSummary(page, { subtotal: "$80.00", discount: "-$0.00", shipping: "$0.00", total: "$80.00" });
});

test("applying a second code replaces the first", async ({ page }) => {
  await apply(page, "SAVE10");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");

  await apply(page, "FREESHIP");
  await expect(page.locator("#cp-applied-code")).toHaveText("FREESHIP");
  await expectSummary(page, { subtotal: "$80.00", discount: "-$0.00", shipping: "$0.00", total: "$80.00" });

  await apply(page, "SAVE10");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await expectSummary(page, { subtotal: "$80.00", discount: "-$8.00", shipping: "$6.00", total: "$78.00" });
});

test("an expired code shows an error and leaves the summary unchanged", async ({ page }) => {
  await apply(page, "EXPIRED1");
  await expect(page.getByRole("alert")).toHaveText("That coupon has expired");
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, ORIGINAL);
});

test("an unknown code shows an error and leaves the summary unchanged", async ({ page }) => {
  await apply(page, "NOPE123");
  await expect(page.getByRole("alert")).toHaveText("Unknown coupon code");
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, ORIGINAL);
});

test("a rejected code leaves a previously applied coupon in place", async ({ page }) => {
  await apply(page, "SAVE10");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");

  await apply(page, "EXPIRED1");
  await expect(page.getByRole("alert")).toHaveText("That coupon has expired");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await expectSummary(page, { subtotal: "$80.00", discount: "-$8.00", shipping: "$6.00", total: "$78.00" });
});

test("Remove takes the coupon off and restores the original summary", async ({ page }) => {
  await apply(page, "SAVE10");
  await expect(page.locator("#cp-applied")).toBeVisible();

  await page.getByRole("button", { name: "Remove" }).click();
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, ORIGINAL);
});

test("the applied coupon survives a reload", async ({ page }) => {
  await apply(page, "SAVE10");
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");

  await page.reload();
  await expect(page.locator("#cp-applied")).toBeVisible();
  await expect(page.locator("#cp-applied-code")).toHaveText("SAVE10");
  await expectSummary(page, { subtotal: "$80.00", discount: "-$8.00", shipping: "$6.00", total: "$78.00" });
});

test("a removed coupon stays removed after a reload", async ({ page }) => {
  await apply(page, "FREESHIP");
  await expect(page.locator("#cp-applied")).toBeVisible();
  await page.getByRole("button", { name: "Remove" }).click();
  await expect(page.locator("#cp-applied")).toBeHidden();

  await page.reload();
  await expect(page.locator("#cp-applied")).toBeHidden();
  await expectSummary(page, ORIGINAL);
});
