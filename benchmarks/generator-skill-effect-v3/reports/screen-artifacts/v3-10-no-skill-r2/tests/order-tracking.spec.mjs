import { expect, test } from "@playwright/test";

const STEPS = ["Ordered", "Packed", "Shipped", "Out for delivery", "Delivered"];

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
});

async function expectTimeline(page, current) {
  const items = page.getByRole("list", { name: "Timeline" }).getByRole("listitem");
  await expect(items).toHaveCount(STEPS.length);
  for (let i = 0; i < STEPS.length; i++) {
    const status = i + 1 < current ? "Done" : i + 1 === current ? "Current" : "Upcoming";
    await expect(items.nth(i)).toHaveText(`${STEPS[i]} — ${status}`);
  }
}

test("starts at the first step", async ({ page }) => {
  await expect(page.locator("#ot-header")).toHaveText("Step 1 of 5: Ordered");
  await expectTimeline(page, 1);
  await expect(page.getByText("Estimated delivery: Thursday 9 October")).toBeVisible();
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeVisible();
  await expect(page.getByText("Cancelled", { exact: true })).toBeHidden();
});

test("advancing walks through every step", async ({ page }) => {
  const advance = page.getByRole("button", { name: "Advance (test seam)" });
  for (let n = 2; n <= 5; n++) {
    await advance.click();
    await expect(page.locator("#ot-header")).toHaveText(`Step ${n} of 5: ${STEPS[n - 1]}`);
    await expectTimeline(page, n);
  }
  await expect(advance).toBeHidden();
});

test("cancel is offered only before Shipped", async ({ page }) => {
  const cancel = page.getByRole("button", { name: "Cancel order" });
  const advance = page.getByRole("button", { name: "Advance (test seam)" });
  await expect(cancel).toBeVisible();
  await advance.click();
  await expect(page.locator("#ot-header")).toHaveText("Step 2 of 5: Packed");
  await expect(cancel).toBeVisible();
  await advance.click();
  await expect(page.locator("#ot-header")).toHaveText("Step 3 of 5: Shipped");
  await expect(cancel).toBeHidden();
  await advance.click();
  await advance.click();
  await expect(page.locator("#ot-header")).toHaveText("Step 5 of 5: Delivered");
  await expect(cancel).toBeHidden();
});

test("cancelling shows the notice and clears the current step", async ({ page }) => {
  await page.getByRole("button", { name: "Cancel order" }).click();
  await expect(page.locator("#ot-header")).toHaveText("Order cancelled");
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(page.getByText(/Estimated delivery/)).toBeHidden();
  await expect(page.getByText("Current", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeHidden();
  await expect(page.getByRole("button", { name: "Advance (test seam)" })).toBeHidden();
});

test("cancelling from Packed keeps earlier steps Done", async ({ page }) => {
  await page.getByRole("button", { name: "Advance (test seam)" }).click();
  await expect(page.locator("#ot-header")).toHaveText("Step 2 of 5: Packed");
  await page.getByRole("button", { name: "Cancel order" }).click();
  await expect(page.locator("#ot-header")).toHaveText("Order cancelled");
  const items = page.getByRole("list", { name: "Timeline" }).getByRole("listitem");
  await expect(items.nth(0)).toHaveText("Ordered — Done");
  await expect(items.nth(1)).toHaveText("Packed — Upcoming");
  await expect(page.getByText("Current", { exact: true })).toHaveCount(0);
});

test("progress survives a reload", async ({ page }) => {
  const advance = page.getByRole("button", { name: "Advance (test seam)" });
  await advance.click();
  await advance.click();
  await expect(page.locator("#ot-header")).toHaveText("Step 3 of 5: Shipped");
  await page.reload();
  await expect(page.locator("#ot-header")).toHaveText("Step 3 of 5: Shipped");
  await expectTimeline(page, 3);
});

test("cancellation survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Cancel order" }).click();
  await expect(page.locator("#ot-header")).toHaveText("Order cancelled");
  await page.reload();
  await expect(page.locator("#ot-header")).toHaveText("Order cancelled");
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(page.getByText(/Estimated delivery/)).toBeHidden();
  await expect(page.getByText("Current", { exact: true })).toHaveCount(0);
});
