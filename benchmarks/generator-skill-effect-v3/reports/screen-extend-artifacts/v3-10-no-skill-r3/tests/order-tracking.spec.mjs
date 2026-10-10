import { expect, test } from "@playwright/test";

const STEPS = ["Ordered", "Packed", "Shipped", "Out for delivery", "Delivered"];

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.locator("#ot-header")).toHaveText("Step 1 of 5: Ordered");
});

async function expectTimeline(page, current) {
  const items = page.getByRole("list", { name: "Timeline" }).getByRole("listitem");
  await expect(items).toHaveCount(5);
  for (let i = 0; i < 5; i++) {
    const status = i + 1 < current ? "Done" : i + 1 === current ? "Current" : "Upcoming";
    await expect(items.nth(i)).toHaveText(`${STEPS[i]} — ${status}`);
  }
  await expect(page.locator("#ot-header")).toHaveText(`Step ${current} of 5: ${STEPS[current - 1]}`);
}

test("initial state is step 1 with estimate and cancel available", async ({ page }) => {
  await expectTimeline(page, 1);
  await expect(page.getByText("Estimated delivery: Thursday 9 October")).toBeVisible();
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeVisible();
  await expect(page.getByText("Cancelled", { exact: true })).toBeHidden();
});

test("advance walks through every step", async ({ page }) => {
  const advance = page.getByRole("button", { name: "Advance (test seam)" });
  for (let step = 2; step <= 5; step++) {
    await advance.click();
    await expectTimeline(page, step);
  }
  await expect(advance).toBeHidden();
});

test("cancel is offered only before Shipped", async ({ page }) => {
  const cancel = page.getByRole("button", { name: "Cancel order" });
  const advance = page.getByRole("button", { name: "Advance (test seam)" });
  await advance.click();
  await expectTimeline(page, 2);
  await expect(cancel).toBeVisible();
  await advance.click();
  await expectTimeline(page, 3);
  await expect(cancel).toBeHidden();
  await advance.click();
  await expect(cancel).toBeHidden();
});

test("progress survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Advance (test seam)" }).click();
  await page.getByRole("button", { name: "Advance (test seam)" }).click();
  await expectTimeline(page, 3);
  await page.reload();
  await expectTimeline(page, 3);
});

test("cancelling shows notice, hides estimate, no current step", async ({ page }) => {
  await page.getByRole("button", { name: "Cancel order" }).click();
  await expect(page.locator("#ot-header")).toHaveText("Order cancelled");
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(page.getByText("Estimated delivery")).toBeHidden();
  await expect(page.getByText("Current", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeHidden();
});

test("cancellation survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Advance (test seam)" }).click();
  await page.getByRole("button", { name: "Cancel order" }).click();
  await expect(page.locator("#ot-header")).toHaveText("Order cancelled");
  await page.reload();
  await expect(page.locator("#ot-header")).toHaveText("Order cancelled");
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(page.getByText("Estimated delivery")).toBeHidden();
  await expect(page.locator(".step-current")).toHaveCount(0);
});
