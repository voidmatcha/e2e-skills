import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

async function sendAndWait(page, n) {
  await page.getByRole("button", { name: "Send test notification" }).click();
  await expect(page.getByText(`${n} sent`, { exact: true })).toBeVisible();
}

test("sending shows a toast in the Notifications region and bumps the counter", async ({ page }) => {
  const region = page.getByRole("region", { name: "Notifications" });
  await expect(page.getByText("0 sent", { exact: true })).toBeVisible();
  await sendAndWait(page, 1);
  await expect(region.getByText("Test notification sent")).toBeVisible();
  await sendAndWait(page, 2);
  await expect(region.getByText("Test notification sent")).toHaveCount(2);
});

test("Dismiss notification removes only that toast", async ({ page }) => {
  const region = page.getByRole("region", { name: "Notifications" });
  await sendAndWait(page, 1);
  await sendAndWait(page, 2);
  const toasts = region.locator(".toast");
  await expect(toasts).toHaveCount(2);
  const secondSerial = await toasts.nth(1).getAttribute("data-serial");
  await toasts.first().getByRole("button", { name: "Dismiss notification" }).click();
  await expect(toasts).toHaveCount(1);
  await expect(toasts.first()).toHaveAttribute("data-serial", secondSerial);
});

test("an untouched toast disappears on its own after about two seconds", async ({ page }) => {
  const region = page.getByRole("region", { name: "Notifications" });
  await sendAndWait(page, 1);
  await expect(region.getByText("Test notification sent")).toBeVisible();
  await page.waitForTimeout(1000);
  await expect(region.getByText("Test notification sent")).toBeVisible();
  await expect(region.getByText("Test notification sent")).toBeHidden({ timeout: 3000 });
});

test("at most three toasts are shown; a fourth drops the oldest", async ({ page }) => {
  const region = page.getByRole("region", { name: "Notifications" });
  const toasts = region.locator(".toast");
  for (let i = 1; i <= 3; i++) await sendAndWait(page, i);
  await expect(toasts).toHaveCount(3);
  const before = await toasts.evaluateAll((els) => els.map((e) => e.dataset.serial));
  await sendAndWait(page, 4);
  await expect(toasts).toHaveCount(3);
  const after = await toasts.evaluateAll((els) => els.map((e) => e.dataset.serial));
  expect(after.slice(0, 2)).toEqual(before.slice(1));
  expect(after).not.toContain(before[0]);
});

test("the Notifications region is a polite live region", async ({ page }) => {
  await expect(page.getByRole("region", { name: "Notifications" })).toHaveAttribute("aria-live", "polite");
});
