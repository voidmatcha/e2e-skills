import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

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

test("sends a test notification and updates the sent counter", async ({ page }) => {
  const notifications = page.getByRole("region", { name: "Notifications", exact: true });

  await expect(notifications).toHaveAttribute("aria-live", "polite");

  await sendTestNotification(page);

  await expect(notifications.getByText("Test notification sent", { exact: true })).toHaveCount(1);
  await expect(page.getByText("1 sent")).toBeVisible();
});

test("dismisses only the selected notification toast", async ({ page }) => {
  const notifications = page.getByRole("region", { name: "Notifications", exact: true });
  const firstToast = notifications.locator('[data-serial="1"]');
  const secondToast = notifications.locator('[data-serial="2"]');

  await sendTestNotification(page);
  await sendTestNotification(page);
  await expect(notifications.getByText("Test notification sent", { exact: true })).toHaveCount(2);

  // JUSTIFIED: Repeated toast controls share the same accessible name; the serial identifies the toast under test.
  await firstToast.getByRole("button", { name: "Dismiss notification", exact: true }).click();

  await expect(firstToast).not.toBeAttached();
  await expect(secondToast).toBeVisible();
  await expect(notifications.getByText("Test notification sent", { exact: true })).toHaveCount(1);
});

test("automatically removes an untouched toast", async ({ page }) => {
  const notifications = page.getByRole("region", { name: "Notifications", exact: true });
  const toastMessage = notifications.getByText("Test notification sent", { exact: true });

  await sendTestNotification(page);

  await expect(toastMessage).toHaveCount(1);
  await expect(toastMessage).toHaveCount(0, { timeout: 3000 });
});

test("keeps at most three toasts and drops the oldest", async ({ page }) => {
  const notifications = page.getByRole("region", { name: "Notifications", exact: true });

  await sendTestNotification(page);
  await sendTestNotification(page);
  await sendTestNotification(page);
  await expect(notifications.locator('[data-serial="1"]')).toBeVisible();
  await sendTestNotification(page);

  await expect(notifications.getByText("Test notification sent", { exact: true })).toHaveCount(3);
  await expect(notifications.locator('[data-serial="1"]')).not.toBeAttached();
  await expect(notifications.locator('[data-serial="2"]')).toBeVisible();
  await expect(notifications.locator('[data-serial="3"]')).toBeVisible();
  await expect(notifications.locator('[data-serial="4"]')).toBeVisible();
});
