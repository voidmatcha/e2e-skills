import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

const sendTestNotification = async (page, sentCount) => {
  await page.getByRole("button", { name: "Send test notification" }).click();
  if (sentCount !== undefined) {
    await expect(page.locator("#nt-count")).toHaveText(`${sentCount} sent`);
  }
};

const expectToastSerials = async (toasts, serials) => {
  await expect.poll(async () => toasts.evaluateAll((els) => els.map((el) => el.dataset.serial))).toEqual(serials);
};

test("send test notification shows a live-region toast and bumps the sent counter", async ({ page }) => {
  const notifications = page.getByRole("region", { name: "Notifications" });

  await expect(notifications).toHaveAttribute("aria-live", "polite");
  await sendTestNotification(page, 1);

  await expect(notifications.getByText("Test notification sent")).toBeVisible();
  await expect(page.locator("#nt-count")).toHaveText("1 sent");
});

test("dismiss notification removes only that toast", async ({ page }) => {
  const toasts = page.locator(".toast");

  await sendTestNotification(page, 1);
  await sendTestNotification(page, 2);
  await sendTestNotification(page, 3);

  await expect(toasts).toHaveCount(3);
  await toasts.nth(1).getByRole("button", { name: "Dismiss notification" }).click();

  await expect(toasts).toHaveCount(2);
  await expectToastSerials(toasts, ["1", "3"]);
});

test("toast left alone disappears on its own", async ({ page }) => {
  const toasts = page.locator(".toast");

  await sendTestNotification(page, 1);
  await expect(toasts).toHaveCount(1);

  await expect(toasts).toHaveCount(0, { timeout: 3000 });
});

test("shows at most three toasts and drops the oldest", async ({ page }) => {
  const toasts = page.locator(".toast");

  await sendTestNotification(page, 1);
  await sendTestNotification(page, 2);
  await sendTestNotification(page, 3);
  await sendTestNotification(page, 4);

  await expect(toasts).toHaveCount(3);
  await expectToastSerials(toasts, ["2", "3", "4"]);
});
