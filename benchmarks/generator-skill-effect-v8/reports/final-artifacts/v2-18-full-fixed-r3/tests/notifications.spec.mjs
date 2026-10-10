import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

async function sendTestNotification(page) {
  const notificationRequest = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/test-notification") &&
      response.request().method() === "POST",
  );

  await page.getByRole("button", { name: /^Send test notification$/ }).click();

  const response = await notificationRequest;
  expect(response.status()).toBe(201);
}

test("sends a test notification and updates the sent counter", async ({ page }) => {
  const notifications = page.getByRole("region", { name: /^Notifications$/ });

  await sendTestNotification(page);

  await expect(notifications.getByText("Test notification sent")).toBeVisible();
  await expect(page.getByText("1 sent")).toBeVisible();
});

test("announces notifications from a polite live region", async ({ page }) => {
  await expect(page.getByRole("region", { name: /^Notifications$/ })).toHaveAttribute(
    "aria-live",
    "polite",
  );
});

test("dismisses only the selected notification", async ({ page }) => {
  const notifications = page.getByRole("region", { name: /^Notifications$/ });
  const toasts = notifications.locator("[data-serial]");

  await sendTestNotification(page);
  await sendTestNotification(page);
  await expect(toasts).toHaveCount(2);

  // JUSTIFIED: all visible dismiss buttons intentionally share the same name.
  await notifications.getByRole("button", { name: /^Dismiss notification$/ }).first().click();

  await expect(toasts).toHaveCount(1);
  await expect(notifications.getByText("Test notification sent")).toBeVisible();
});

test("removes an untouched notification automatically", async ({ page }) => {
  const notifications = page.getByRole("region", { name: /^Notifications$/ });
  const toasts = notifications.locator("[data-serial]");
  let removedAfterMs;

  await sendTestNotification(page);
  await expect(toasts).toHaveCount(1);

  const visibleAt = Date.now();
  await expect
    .poll(
      async () => {
        if (removedAfterMs === undefined && (await toasts.count()) === 0) {
          removedAfterMs = Date.now() - visibleAt;
        }
        return removedAfterMs;
      },
      { timeout: 3000 },
    )
    .toBeGreaterThanOrEqual(1800);
  expect(removedAfterMs).toBeLessThan(3000);
});

test("keeps at most three notifications and drops the oldest", async ({ page }) => {
  const notifications = page.getByRole("region", { name: /^Notifications$/ });
  const toasts = notifications.locator("[data-serial]");

  await sendTestNotification(page);
  await sendTestNotification(page);
  await sendTestNotification(page);
  await sendTestNotification(page);

  await expect(toasts).toHaveCount(3);
  await expect
    .poll(() => toasts.evaluateAll((elements) => elements.map((element) => element.dataset.serial)))
    .toEqual(["2", "3", "4"]);
  await expect(page.getByText("4 sent")).toBeVisible();
});
