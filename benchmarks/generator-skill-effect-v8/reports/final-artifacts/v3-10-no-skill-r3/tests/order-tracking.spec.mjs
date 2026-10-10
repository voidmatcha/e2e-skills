import { expect, test } from "@playwright/test";

const steps = ["Ordered", "Packed", "Shipped", "Out for delivery", "Delivered"];

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

async function expectProgress(page, currentStep) {
  await expect(page.locator("#ot-header")).toHaveText(`Step ${currentStep} of 5: ${steps[currentStep - 1]}`);

  const timeline = page.getByRole("list", { name: "Timeline" });
  await expect(timeline.getByRole("listitem")).toHaveCount(5);

  for (const [index, name] of steps.entries()) {
    const stepNumber = index + 1;
    const status = stepNumber < currentStep ? "Done" : stepNumber === currentStep ? "Current" : "Upcoming";
    await expect(timeline.getByRole("listitem").nth(index)).toHaveText(`${name} — ${status}`);
  }
}

async function advance(page) {
  await page.getByRole("button", { name: "Advance (test seam)" }).click();
}

test("shows one current timeline step and advances through all five steps", async ({ page }) => {
  await page.goto("/");

  await expectProgress(page, 1);
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeVisible();

  await advance(page);
  await expectProgress(page, 2);
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeVisible();

  await advance(page);
  await expectProgress(page, 3);
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeHidden();

  await advance(page);
  await expectProgress(page, 4);
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeHidden();

  await advance(page);
  await expectProgress(page, 5);
  await expect(page.getByRole("button", { name: "Advance (test seam)" })).toBeHidden();
});

test("persists progress after a reload", async ({ page }) => {
  await page.goto("/");

  await advance(page);
  await advance(page);
  await expectProgress(page, 3);

  await page.reload();

  await expectProgress(page, 3);
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeHidden();
});

test("cancels before shipped and persists the cancelled state after reload", async ({ page }) => {
  await page.goto("/");

  await advance(page);
  await expectProgress(page, 2);
  await page.getByRole("button", { name: "Cancel order" }).click();

  await expect(page.locator("#ot-header")).toHaveText("Order cancelled");
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(page.getByText("Estimated delivery: Thursday 9 October")).toBeHidden();
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeHidden();
  await expect(page.getByRole("button", { name: "Advance (test seam)" })).toBeHidden();
  await expect(page.locator(".step-current")).toHaveCount(0);

  await page.reload();

  await expect(page.locator("#ot-header")).toHaveText("Order cancelled");
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(page.getByText("Estimated delivery: Thursday 9 October")).toBeHidden();
  await expect(page.locator(".step-current")).toHaveCount(0);
});
