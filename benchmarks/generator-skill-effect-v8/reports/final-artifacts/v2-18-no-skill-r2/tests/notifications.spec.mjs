import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

const sendTestNotification = async (page) => {
  await page.getByRole("button", { name: "Send test notification" }).click();
};

const notificationsRegion = (page) =>
  page.getByRole("region", { name: "Notifications" });

test("sends a test notification, announces it, and increments the sent count", async ({
  page,
}) => {
  const region = notificationsRegion(page);

  await expect(region).toHaveAttribute("aria-live", "polite");

  await sendTestNotification(page);

  await expect(region.getByText("Test notification sent")).toBeVisible();
  await expect(page.locator("#nt-count")).toHaveText("1 sent");
});

test("dismisses only the selected notification", async ({ page }) => {
  const region = notificationsRegion(page);
  const toasts = region.locator(".toast");

  await sendTestNotification(page);
  await sendTestNotification(page);
  await sendTestNotification(page);
  await expect(toasts).toHaveCount(3);

  await toasts.nth(1).getByRole("button", { name: "Dismiss notification" }).click();

  await expect(toasts).toHaveCount(2);
  await expect.poll(() => toasts.evaluateAll((nodes) => nodes.map((node) => node.dataset.serial))).toEqual(["1", "3"]);
});

test("auto-dismisses a notification that is left alone", async ({ page }) => {
  const region = notificationsRegion(page);
  const toast = region.locator(".toast");

  await sendTestNotification(page);
  await expect(toast).toHaveCount(1);

  await expect(toast).toHaveCount(0, { timeout: 3000 });
});

test("keeps at most three notifications and drops the oldest", async ({ page }) => {
  const region = notificationsRegion(page);
  const toasts = region.locator(".toast");

  await sendTestNotification(page);
  await sendTestNotification(page);
  await sendTestNotification(page);
  await sendTestNotification(page);

  await expect(toasts).toHaveCount(3);
  await expect.poll(() => toasts.evaluateAll((nodes) => nodes.map((node) => node.dataset.serial))).toEqual(["2", "3", "4"]);
  await expect(page.locator("#nt-count")).toHaveText("4 sent");
});
