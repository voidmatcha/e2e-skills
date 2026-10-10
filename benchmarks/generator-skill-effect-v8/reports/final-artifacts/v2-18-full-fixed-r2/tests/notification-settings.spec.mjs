import { expect, test } from "@playwright/test";

const sendTestNotification = async (page) => {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/test-notification") &&
      response.request().method() === "POST",
  );

  await page.getByRole("button", { name: "Send test notification", exact: true }).click();

  const response = await responsePromise;
  expect(response.status()).toBe(201);
};

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("sends a test notification and updates the sent counter", async ({ page }) => {
  const notifications = page.getByRole("region", { name: "Notifications", exact: true });

  await sendTestNotification(page);

  await expect(notifications.getByText("Test notification sent")).toHaveCount(1);
  await expect(page.getByText(/^1 sent$/)).toBeVisible();
  await expect(notifications).toHaveAttribute("aria-live", "polite");
});

test("dismisses only the selected notification", async ({ page }) => {
  const notifications = page.getByRole("region", { name: "Notifications", exact: true });
  // JUSTIFIED: Toasts have identical text and button names; data-serial identifies the selected toast.
  const selectedToast = notifications.locator('[data-serial="1"]');
  // JUSTIFIED: Toasts have identical text and button names; data-serial identifies the untouched toast.
  const untouchedToast = notifications.locator('[data-serial="2"]');

  await sendTestNotification(page);
  await sendTestNotification(page);
  await expect(selectedToast).toHaveCount(1);
  await expect(untouchedToast).toHaveCount(1);
  await expect(selectedToast.getByRole("button", { name: "Dismiss notification", exact: true })).toHaveCount(1);
  await expect(untouchedToast.getByRole("button", { name: "Dismiss notification", exact: true })).toHaveCount(1);

  await selectedToast.getByRole("button", { name: "Dismiss notification", exact: true }).click();

  await expect(selectedToast).toHaveCount(0);
  await expect(untouchedToast).toHaveCount(1);
});

test("removes an untouched notification automatically", async ({ page }) => {
  await page.clock.install();
  const notifications = page.getByRole("region", { name: "Notifications", exact: true });
  const toast = notifications.getByText("Test notification sent");

  await sendTestNotification(page);
  await expect(toast).toHaveCount(1);

  await page.clock.fastForward(1_500);
  await expect(toast).toHaveCount(1);
  await page.clock.fastForward(500);
  await expect(toast).toHaveCount(0);
});

test("shows at most three notifications and drops the oldest", async ({ page }) => {
  const notifications = page.getByRole("region", { name: "Notifications", exact: true });
  const toasts = notifications.getByText("Test notification sent");
  // JUSTIFIED: Toasts have identical text and button names; data-serial is the only exposed identity for oldest-drop behavior.

  await sendTestNotification(page);
  await sendTestNotification(page);
  await sendTestNotification(page);
  await expect(toasts).toHaveCount(3);
  await expect(notifications.locator('[data-serial="1"]')).toHaveCount(1);

  await sendTestNotification(page);

  await expect(toasts).toHaveCount(3);
  await expect(notifications.locator('[data-serial="1"]')).toHaveCount(0);
  await expect(notifications.locator('[data-serial="2"]')).toHaveCount(1);
  await expect(notifications.locator('[data-serial="3"]')).toHaveCount(1);
  await expect(notifications.locator('[data-serial="4"]')).toHaveCount(1);
});
