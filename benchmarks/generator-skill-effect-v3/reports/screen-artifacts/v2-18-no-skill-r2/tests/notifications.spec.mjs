import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  // Fake timers so auto-dismiss is deterministic and toasts don't expire mid-test.
  await page.clock.install();
  await page.goto("/");
});

const region = (page) => page.getByRole("region", { name: "Notifications" });
const toasts = (page) => region(page).locator(".toast");
const send = (page) => page.getByRole("button", { name: "Send test notification" });

// Click and wait until the toast count has settled to `shown`, with the counter at `sent`.
async function sendAndWait(page, sent, shown) {
  await send(page).click();
  await expect(page.getByText(`${sent} sent`)).toBeVisible();
  await expect(toasts(page)).toHaveCount(shown);
}

test("sending a test notification shows a toast and bumps the counter", async ({ page }) => {
  await expect(page.getByText("0 sent")).toBeVisible();
  await send(page).click();
  await expect(region(page).getByText("Test notification sent")).toBeVisible();
  await expect(page.getByText("1 sent")).toBeVisible();
  await send(page).click();
  await expect(page.getByText("2 sent")).toBeVisible();
});

test("the Notifications region is a polite live region", async ({ page }) => {
  await expect(region(page)).toHaveAttribute("aria-live", "polite");
});

test("Dismiss notification removes only that toast", async ({ page }) => {
  await sendAndWait(page, 1, 1);
  await sendAndWait(page, 2, 2);
  await sendAndWait(page, 3, 3);
  const serials = await toasts(page).evaluateAll((els) => els.map((e) => e.dataset.serial));

  await toasts(page).nth(1).getByRole("button", { name: "Dismiss notification" }).click();

  await expect(toasts(page)).toHaveCount(2);
  const remaining = await toasts(page).evaluateAll((els) => els.map((e) => e.dataset.serial));
  expect(remaining).toEqual([serials[0], serials[2]]);
});

test("a toast disappears on its own after about two seconds", async ({ page }) => {
  await sendAndWait(page, 1, 1);
  await page.clock.fastForward(1500);
  await expect(toasts(page)).toHaveCount(1);
  await page.clock.fastForward(600);
  await expect(toasts(page)).toHaveCount(0);
});

test("at most three toasts are shown; a fourth drops the oldest", async ({ page }) => {
  await sendAndWait(page, 1, 1);
  await sendAndWait(page, 2, 2);
  await sendAndWait(page, 3, 3);
  const before = await toasts(page).evaluateAll((els) => els.map((e) => e.dataset.serial));

  await sendAndWait(page, 4, 3);
  const after = await toasts(page).evaluateAll((els) => els.map((e) => e.dataset.serial));
  expect(after.slice(0, 2)).toEqual(before.slice(1));
  expect(after).not.toContain(before[0]);
});
