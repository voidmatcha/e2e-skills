import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

const serials = (region) =>
  region.locator(".toast").evaluateAll((toasts) => toasts.map((t) => t.dataset.serial));

async function sendN(page, n) {
  const send = page.getByRole("button", { name: "Send test notification" });
  for (let i = 1; i <= n; i++) {
    await send.click();
    await expect(page.locator("#nt-count")).toHaveText(`${i} sent`);
  }
}

test("sending shows a toast and bumps the counter", async ({ page }) => {
  const region = page.getByRole("region", { name: "Notifications" });
  await expect(page.getByText("0 sent")).toBeVisible();
  await page.getByRole("button", { name: "Send test notification" }).click();
  await expect(region.getByText("Test notification sent")).toBeVisible();
  await expect(page.getByText("1 sent")).toBeVisible();
});

test("dismiss removes only the chosen toast", async ({ page }) => {
  const region = page.getByRole("region", { name: "Notifications" });
  await sendN(page, 3);
  await expect(region.getByRole("button", { name: "Dismiss notification" })).toHaveCount(3);
  expect(await serials(region)).toEqual(["1", "2", "3"]);

  await region.getByRole("button", { name: "Dismiss notification" }).nth(1).click();
  await expect(region.getByRole("button", { name: "Dismiss notification" })).toHaveCount(2);
  expect(await serials(region)).toEqual(["1", "3"]);
});

test("an untouched toast disappears after about two seconds", async ({ page }) => {
  const region = page.getByRole("region", { name: "Notifications" });
  await page.getByRole("button", { name: "Send test notification" }).click();
  const toast = region.getByText("Test notification sent");
  await expect(toast).toBeVisible();
  const start = Date.now();
  await expect(toast).toBeHidden({ timeout: 5000 });
  expect(Date.now() - start).toBeLessThan(3500);
  await expect(page.getByText("1 sent")).toBeVisible();
});

test("shows at most three toasts, dropping the oldest", async ({ page }) => {
  const region = page.getByRole("region", { name: "Notifications" });
  await sendN(page, 4);
  await expect(page.getByText("4 sent")).toBeVisible();
  await expect(region.locator(".toast")).toHaveCount(3);
  expect(await serials(region)).toEqual(["2", "3", "4"]);
});

test("notifications region is a polite live region", async ({ page }) => {
  await expect(page.getByRole("region", { name: "Notifications" })).toHaveAttribute(
    "aria-live",
    "polite",
  );
});
