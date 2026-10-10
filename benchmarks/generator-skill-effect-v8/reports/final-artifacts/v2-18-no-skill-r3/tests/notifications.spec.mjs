import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("announces sent notifications in a polite notifications region", async ({ page }) => {
  const region = page.getByRole("region", { name: "Notifications" });

  await expect(region).toHaveAttribute("aria-live", "polite");

  await page.getByRole("button", { name: "Send test notification" }).click();

  await expect(region.getByText("Test notification sent")).toBeVisible();
  await expect(page.locator("#nt-count")).toHaveText("1 sent");
});

test("dismisses only the selected notification", async ({ page }) => {
  const send = page.getByRole("button", { name: "Send test notification" });
  const toasts = page.locator(".toast");

  await send.click();
  await send.click();
  await send.click();
  await expect(toasts).toHaveCount(3);

  const secondToast = toasts.nth(1);
  const dismissedSerial = await secondToast.getAttribute("data-serial");
  await secondToast.getByRole("button", { name: "Dismiss notification" }).click();

  await expect(page.locator(`.toast[data-serial="${dismissedSerial}"]`)).toHaveCount(0);
  await expect(toasts).toHaveCount(2);
  await expect(toasts).toHaveText(["Test notification sent×", "Test notification sent×"]);
});

test("removes untouched notifications automatically", async ({ page }) => {
  const region = page.getByRole("region", { name: "Notifications" });

  await page.getByRole("button", { name: "Send test notification" }).click();
  await expect(region.getByText("Test notification sent")).toBeVisible();

  await expect(page.locator(".toast")).toHaveCount(0, { timeout: 3500 });
});

test("keeps only the three newest notifications", async ({ page }) => {
  const send = page.getByRole("button", { name: "Send test notification" });
  const toasts = page.locator(".toast");

  await send.click();
  await send.click();
  await send.click();
  await send.click();

  await expect(toasts).toHaveCount(3);
  await expect(toasts).toHaveText([
    "Test notification sent×",
    "Test notification sent×",
    "Test notification sent×",
  ]);
  await expect(toasts.first()).toHaveAttribute("data-serial", "2");
  await expect(toasts.nth(1)).toHaveAttribute("data-serial", "3");
  await expect(toasts.nth(2)).toHaveAttribute("data-serial", "4");
  await expect(page.locator("#nt-count")).toHaveText("4 sent");
});
