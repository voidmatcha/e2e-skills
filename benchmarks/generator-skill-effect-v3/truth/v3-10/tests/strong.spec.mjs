import { expect, test } from "@playwright/test";

const steps = (page) => page.getByRole("list", { name: "Timeline" }).getByRole("listitem");
const header = (page) => page.getByText(/^(Step \d of 5: .+|Order cancelled)$/);
const advance = (page) => page.getByRole("button", { name: "Advance (test seam)" });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(header(page)).toHaveText("Step 1 of 5: Ordered");
});

test("advancing moves the single Current marker and the header, and persists", async ({ page }) => {
  await expect(steps(page)).toHaveText([/Ordered — Current/, /Packed — Upcoming/, /Shipped — Upcoming/, /Out for delivery — Upcoming/, /Delivered — Upcoming/]);
  await advance(page).click();
  await expect(header(page)).toHaveText("Step 2 of 5: Packed");
  await expect(steps(page)).toHaveText([/Ordered — Done/, /Packed — Current/, /Shipped — Upcoming/, /Out for delivery — Upcoming/, /Delivered — Upcoming/]);
  await expect(steps(page).filter({ hasText: "Current" })).toHaveCount(1);
  await page.reload();
  await expect(header(page)).toHaveText("Step 2 of 5: Packed");
  await expect(steps(page).filter({ hasText: "Current" })).toHaveCount(1);
});

test("cancel is offered only before Shipped and cancelling clears the Current marker", async ({ page }) => {
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeVisible();
  await advance(page).click();
  await expect(header(page)).toHaveText("Step 2 of 5: Packed");
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeVisible();
  await advance(page).click();
  await expect(header(page)).toHaveText("Step 3 of 5: Shipped");
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeHidden();
  await page.request.post("/api/reset");
  await page.reload();
  await page.getByRole("button", { name: "Cancel order" }).click();
  await expect(header(page)).toHaveText("Order cancelled");
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(page.getByText(/Estimated delivery/)).toBeHidden();
  await expect(steps(page).filter({ hasText: "Current" })).toHaveCount(0);
  await page.reload();
  await expect(header(page)).toHaveText("Order cancelled");
});
