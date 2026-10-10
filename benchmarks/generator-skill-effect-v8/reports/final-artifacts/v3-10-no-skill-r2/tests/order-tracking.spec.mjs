import { expect, test } from "@playwright/test";

const STEPS = ["Ordered", "Packed", "Shipped", "Out for delivery", "Delivered"];

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

async function expectTimeline(page, currentStep) {
  await expect(page.locator("#ot-header")).toHaveText(
    `Step ${currentStep} of ${STEPS.length}: ${STEPS[currentStep - 1]}`,
  );
  await expect(page.locator("#ot-steps li")).toHaveCount(STEPS.length);
  await expect(page.locator("#ot-steps .step-name")).toHaveText(STEPS);
  await expect(page.locator("#ot-steps .step-status")).toHaveText(
    STEPS.map((_, index) => {
      const step = index + 1;
      if (step < currentStep) return "Done";
      if (step === currentStep) return "Current";
      return "Upcoming";
    }),
  );
}

async function expectCancelled(page) {
  await expect(page.locator("#ot-header")).toHaveText("Order cancelled");
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(page.locator("#ot-eta")).toBeHidden();
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeHidden();
  await expect(page.getByRole("button", { name: "Advance (test seam)" })).toBeHidden();
  await expect(page.locator("#ot-steps .step-status", { hasText: "Current" })).toHaveCount(0);
}

test("shows timeline progress, advances through each step, and persists across reloads", async ({ page }) => {
  await page.goto("/");

  await expectTimeline(page, 1);
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeVisible();

  await page.getByRole("button", { name: "Advance (test seam)" }).click();
  await expectTimeline(page, 2);
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeVisible();

  await page.getByRole("button", { name: "Advance (test seam)" }).click();
  await expectTimeline(page, 3);
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeHidden();

  await page.reload();
  await expectTimeline(page, 3);
  await expect(page.getByRole("button", { name: "Cancel order" })).toBeHidden();

  await page.getByRole("button", { name: "Advance (test seam)" }).click();
  await expectTimeline(page, 4);

  await page.getByRole("button", { name: "Advance (test seam)" }).click();
  await expectTimeline(page, 5);
  await expect(page.getByRole("button", { name: "Advance (test seam)" })).toBeHidden();

  await page.reload();
  await expectTimeline(page, 5);
  await expect(page.getByRole("button", { name: "Advance (test seam)" })).toBeHidden();
});

test("cancels before shipping and persists the cancelled state across reloads", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Advance (test seam)" }).click();
  await expectTimeline(page, 2);

  await page.getByRole("button", { name: "Cancel order" }).click();
  await expectCancelled(page);
  await expect(page.locator("#ot-steps .step-status")).toHaveText([
    "Done",
    "Upcoming",
    "Upcoming",
    "Upcoming",
    "Upcoming",
  ]);

  await page.reload();
  await expectCancelled(page);
  await expect(page.locator("#ot-steps .step-status")).toHaveText([
    "Done",
    "Upcoming",
    "Upcoming",
    "Upcoming",
    "Upcoming",
  ]);
});
