import { expect, test } from "@playwright/test";

const steps = ["Ordered", "Packed", "Shipped", "Out for delivery", "Delivered"];

const timeline = (page) =>
  page.getByRole("list", { name: "Timeline", exact: true }).getByRole("listitem");

async function resetOrder(page) {
  const response = await page.request.post("/api/reset");
  expect(response.ok()).toBeTruthy();
}

async function expectStep(page, currentStep) {
  await expect(
    page.getByText(`Step ${currentStep} of ${steps.length}: ${steps[currentStep - 1]}`),
  ).toBeVisible();

  await expect(timeline(page)).toHaveText(
    steps.map((name, index) => {
      const stepNumber = index + 1;
      if (stepNumber < currentStep) return `${name} — Done`;
      if (stepNumber === currentStep) return `${name} — Current`;
      return `${name} — Upcoming`;
    }),
  );
}

test.beforeEach(async ({ page }) => {
  await resetOrder(page);
  await page.goto("/");
});

test("shows exactly one current timeline step and advances through delivery", async ({
  page,
}) => {
  await expectStep(page, 1);

  for (let nextStep = 2; nextStep <= steps.length; nextStep += 1) {
    const advanceRequest = page.waitForRequest(
      (request) =>
        request.method() === "POST" &&
        new URL(request.url()).pathname === "/api/dev/advance",
    );
    await page
      .getByRole("button", { name: "Advance (test seam)", exact: true })
      .click();
    await advanceRequest;

    await expectStep(page, nextStep);
  }

  await expect(
    page.getByRole("button", { name: "Advance (test seam)", exact: true }),
  ).toHaveCount(0);
});

test("persists progress after a reload", async ({ page }) => {
  const advanceRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/dev/advance",
  );
  await page
    .getByRole("button", { name: "Advance (test seam)", exact: true })
    .click();
  await advanceRequest;

  await expect(page.getByText("Step 2 of 5: Packed")).toBeVisible();

  await page.reload();

  await expectStep(page, 2);
});

test("cancels before shipping and persists the cancelled state", async ({ page }) => {
  await expect(page.getByText("Estimated delivery: Thursday 9 October")).toBeVisible();
  await expect(timeline(page).filter({ hasText: "Current" })).toHaveCount(1);

  const cancelRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/order/cancel",
  );
  await page.getByRole("button", { name: "Cancel order", exact: true }).click();
  await cancelRequest;

  await expect(page.getByText("Order cancelled")).toBeVisible();
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(page.getByText("Estimated delivery: Thursday 9 October")).toBeHidden();
  await expect(timeline(page).filter({ hasText: "Current" })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Cancel order", exact: true }),
  ).toHaveCount(0);

  await page.reload();

  await expect(page.getByText("Order cancelled")).toBeVisible();
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(page.getByText("Estimated delivery: Thursday 9 October")).toBeHidden();
  await expect(timeline(page).filter({ hasText: "Current" })).toHaveCount(0);
});

test("does not offer cancellation once the order has shipped", async ({ page }) => {
  await expect(
    page.getByRole("button", { name: "Cancel order", exact: true }),
  ).toBeVisible();

  for (let nextStep = 2; nextStep <= 3; nextStep += 1) {
    const advanceRequest = page.waitForRequest(
      (request) =>
        request.method() === "POST" &&
        new URL(request.url()).pathname === "/api/dev/advance",
    );
    await page
      .getByRole("button", { name: "Advance (test seam)", exact: true })
      .click();
    await advanceRequest;
  }

  await expect(page.getByText("Step 3 of 5: Shipped")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Cancel order", exact: true }),
  ).toHaveCount(0);

  await page.reload();

  await expect(page.getByText("Step 3 of 5: Shipped")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Cancel order", exact: true }),
  ).toHaveCount(0);
});
