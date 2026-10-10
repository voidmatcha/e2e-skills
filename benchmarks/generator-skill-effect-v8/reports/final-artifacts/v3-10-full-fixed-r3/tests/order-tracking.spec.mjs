import { expect, test } from "@playwright/test";

const STEPS = ["Ordered", "Packed", "Shipped", "Out for delivery", "Delivered"];

const timeline = (page) => page.getByRole("list", { name: "Timeline", exact: true });
const stepItem = (page, name) => timeline(page).getByRole("listitem").filter({ hasText: name });
const statusText = (page, status) => timeline(page).getByText(status, { exact: true });
const estimatedDelivery = (page) => page.getByText("Estimated delivery: Thursday 9 October", { exact: true });
function cancelButton(page) {
  return page.getByRole("button", { name: "Cancel order", exact: true, includeHidden: true });
}

function advanceButton(page) {
  return page.getByRole("button", { name: /^Advance \(test seam\)$/, includeHidden: true });
}

async function expectOrderStep(page, stepNumber) {
  const currentStep = STEPS[stepNumber - 1];

  await expect(page.getByText(`Step ${stepNumber} of ${STEPS.length}: ${currentStep}`, { exact: true })).toBeVisible();
  await expect(statusText(page, "Current")).toHaveCount(1);
  await expect(statusText(page, "Done")).toHaveCount(stepNumber - 1);
  await expect(statusText(page, "Upcoming")).toHaveCount(STEPS.length - stepNumber);

  for (const [index, name] of STEPS.entries()) {
    const expectedStatus =
      index + 1 < stepNumber ? "Done" : index + 1 === stepNumber ? "Current" : "Upcoming";
    await expect(stepItem(page, name)).toContainText(`${name} — ${expectedStatus}`);
  }
}

async function expectSuccessfulWrite(responsePromise) {
  const response = await responsePromise;
  expect(response.status()).toBe(200);
}

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shows one current timeline step and persists each advance", async ({ page }) => {
  await page.goto("/");
  await expectOrderStep(page, 1);
  await expect(cancelButton(page)).toBeVisible();

  for (let stepNumber = 2; stepNumber <= STEPS.length; stepNumber += 1) {
    const advanceResponse = page.waitForResponse(
      (response) => response.url().endsWith("/api/dev/advance") && response.request().method() === "POST",
    );

    await advanceButton(page).click();
    await expectSuccessfulWrite(advanceResponse);
    await expectOrderStep(page, stepNumber);

    await page.reload();
    await expectOrderStep(page, stepNumber);
  }

  await expect(advanceButton(page)).toBeHidden();
});

test("cancels before shipment and persists the cancelled state", async ({ page }) => {
  await page.goto("/");
  await expectOrderStep(page, 1);
  await expect(estimatedDelivery(page)).toBeVisible();
  await expect(cancelButton(page)).toBeVisible();

  const cancelResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/order/cancel") && response.request().method() === "POST",
  );

  await cancelButton(page).click();
  await expectSuccessfulWrite(cancelResponse);

  await expect(page.getByText("Order cancelled", { exact: true })).toBeVisible();
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(estimatedDelivery(page)).toBeHidden();
  await expect(statusText(page, "Current")).toHaveCount(0);
  await expect(cancelButton(page)).toBeHidden();

  await page.reload();
  await expect(page.getByText("Order cancelled", { exact: true })).toBeVisible();
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(estimatedDelivery(page)).toBeHidden();
  await expect(statusText(page, "Current")).toHaveCount(0);
});

test("does not offer cancellation once the order has shipped", async ({ page }) => {
  await page.goto("/");
  await expect(cancelButton(page)).toBeVisible();

  for (let stepNumber = 2; stepNumber <= 3; stepNumber += 1) {
    const advanceResponse = page.waitForResponse(
      (response) => response.url().endsWith("/api/dev/advance") && response.request().method() === "POST",
    );

    await advanceButton(page).click();
    await expectSuccessfulWrite(advanceResponse);
    await expectOrderStep(page, stepNumber);
  }

  await expect(cancelButton(page)).toBeHidden();

  await page.reload();
  await expectOrderStep(page, 3);
  await expect(cancelButton(page)).toBeHidden();
});
