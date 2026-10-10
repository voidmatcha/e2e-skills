import { expect, test } from "@playwright/test";

const summary = (page) => page.getByRole("definition");
const field = (page, index) => summary(page).nth(index);

async function apply(page, code) {
  await page.getByLabel("Coupon code").fill(code);
  await page.getByRole("button", { name: "Apply" }).click();
}

async function expectSummary(page, subtotal, discount, shipping, total) {
  await expect(field(page, 0)).toHaveText(subtotal);
  await expect(field(page, 1)).toHaveText(discount);
  await expect(field(page, 2)).toHaveText(shipping);
  await expect(field(page, 3)).toHaveText(total);
}

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expectSummary(page, "$80.00", "-$0.00", "$6.00", "$86.00");
});

test("SAVE10 and FREESHIP each change the summary, and a second code replaces the first", async ({ page }) => {
  await apply(page, "SAVE10");
  await expect(page.getByText("Applied: SAVE10")).toBeVisible();
  await expectSummary(page, "$80.00", "-$8.00", "$6.00", "$78.00");
  await apply(page, "FREESHIP");
  await expect(page.getByText("Applied: FREESHIP")).toBeVisible();
  await expectSummary(page, "$80.00", "-$0.00", "$0.00", "$80.00");
});

test("expired and unknown codes are rejected without changing the summary", async ({ page }) => {
  await apply(page, "EXPIRED1");
  await expect(page.getByRole("alert")).toHaveText("That coupon has expired");
  await expectSummary(page, "$80.00", "-$0.00", "$6.00", "$86.00");
  await apply(page, "NOPE");
  await expect(page.getByRole("alert")).toHaveText("Unknown coupon code");
  await expectSummary(page, "$80.00", "-$0.00", "$6.00", "$86.00");
  await expect(page.getByText(/Applied:/)).toBeHidden();
});

test("remove restores the original summary", async ({ page }) => {
  await apply(page, "SAVE10");
  await expectSummary(page, "$80.00", "-$8.00", "$6.00", "$78.00");
  await page.getByRole("button", { name: "Remove" }).click();
  await expect(page.getByText(/Applied:/)).toBeHidden();
  await expectSummary(page, "$80.00", "-$0.00", "$6.00", "$86.00");
  await page.reload();
  await expectSummary(page, "$80.00", "-$0.00", "$6.00", "$86.00");
});

test("the applied coupon survives a reload", async ({ page }) => {
  await apply(page, "FREESHIP");
  await expectSummary(page, "$80.00", "-$0.00", "$0.00", "$80.00");
  await page.reload();
  await expect(page.getByText("Applied: FREESHIP")).toBeVisible();
  await expectSummary(page, "$80.00", "-$0.00", "$0.00", "$80.00");
});
