import { expect, test } from "@playwright/test";

const steps = ["Ordered", "Packed", "Shipped", "Out for delivery", "Delivered"];

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

async function expectStep(page, name, status) {
  await expect(
    page
      .getByRole("list", { name: "Timeline" })
      .getByRole("listitem")
      .filter({ hasText: name }),
  ).toHaveText(new RegExp(`^${name} \\u2014 ${status}$`));
}

async function expectTimeline(page, currentStep) {
  await expect(page.getByText(`Step ${currentStep} of 5: ${steps[currentStep - 1]}`)).toBeVisible();
  await expect(page.getByText(/\u2014 Current$/)).toHaveCount(1);

  for (const [index, name] of steps.entries()) {
    let status = "Upcoming";
    if (index + 1 < currentStep) status = "Done";
    if (index + 1 === currentStep) status = "Current";
    await expectStep(page, name, status);
  }
}

async function advanceOrder(page) {
  const response = page.waitForResponse(
    (res) => res.url().endsWith("/api/dev/advance") && res.request().method() === "POST",
  );
  await page.getByRole("button", { name: /^Advance \(test seam\)$/ }).click();
  expect((await response).status()).toBe(200);
}

async function cancelOrder(page) {
  const response = page.waitForResponse(
    (res) => res.url().endsWith("/api/order/cancel") && res.request().method() === "POST",
  );
  await page.getByRole("button", { name: /^Cancel order$/ }).click();
  expect((await response).status()).toBe(200);
}

test("shows the initial order timeline", async ({ page }) => {
  await page.goto("/");

  await expectTimeline(page, 1);
  await expect(page.getByText("Estimated delivery: Thursday 9 October")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Cancel order$/ })).toBeVisible();
});

test("advances through each step and persists progress after reload", async ({ page }) => {
  await page.goto("/");

  for (let step = 1; step <= steps.length; step += 1) {
    await expectTimeline(page, step);
    if (step < steps.length) await advanceOrder(page);
  }

  await expect(page.getByRole("button", { name: /^Advance \(test seam\)$/ })).toBeHidden();
  await page.reload();
  await expectTimeline(page, 5);
});

test("cancels before shipping and persists the cancelled state after reload", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Estimated delivery: Thursday 9 October")).toBeVisible();
  await expect(page.getByText(/\u2014 Current$/)).toHaveCount(1);
  await expect(page.getByRole("button", { name: /^Cancel order$/ })).toBeVisible();
  await advanceOrder(page);

  await cancelOrder(page);

  await expect(page.getByText("Order cancelled")).toBeVisible();
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(page.getByText("Estimated delivery: Thursday 9 October")).toBeHidden();
  await expect(page.getByText(/\u2014 Current$/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Cancel order$/ })).toBeHidden();

  await page.reload();
  await expect(page.getByText("Order cancelled")).toBeVisible();
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(page.getByText("Estimated delivery: Thursday 9 October")).toBeHidden();
  await expect(page.getByText(/\u2014 Current$/)).toHaveCount(0);
});

test("does not offer cancellation once the order is shipped", async ({ page }) => {
  await page.goto("/");
  const cancelButton = page.getByRole("button", { name: /^Cancel order$/ });

  await expect(cancelButton).toBeVisible();
  await advanceOrder(page);
  await advanceOrder(page);

  await expectTimeline(page, 3);
  await expect(cancelButton).toBeHidden();
});
