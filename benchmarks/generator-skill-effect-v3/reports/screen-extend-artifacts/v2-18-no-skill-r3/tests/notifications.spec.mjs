import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  // Fake timers so auto-dismiss is deterministic; fetch still uses the real server.
  await page.clock.install();
  await page.goto("/");
});

const send = (page) => page.getByRole("button", { name: "Send test notification" });
const region = (page) => page.getByRole("region", { name: "Notifications" });
const toasts = (page) => region(page).locator(".toast");

async function sendN(page, n) {
  for (let i = 1; i <= n; i++) {
    await send(page).click();
    await expect(page.locator("#nt-count")).toHaveText(`${i} sent`);
  }
}

// Serial numbers identify toasts, since every toast has the same text.
const serials = (page) => toasts(page).evaluateAll((els) => els.map((e) => e.dataset.serial));

test("sending a test notification shows a toast and bumps the counter", async ({ page }) => {
  await expect(page.getByText("0 sent")).toBeVisible();
  await send(page).click();
  await expect(region(page).getByText("Test notification sent")).toBeVisible();
  await expect(page.getByText("1 sent")).toBeVisible();
  await send(page).click();
  await expect(page.getByText("2 sent")).toBeVisible();
  await expect(toasts(page)).toHaveCount(2);
});

test("Dismiss notification removes only that toast", async ({ page }) => {
  await sendN(page, 3);
  const before = await serials(page);
  expect(before).toHaveLength(3);

  await toasts(page).nth(1).getByRole("button", { name: "Dismiss notification" }).click();

  await expect(toasts(page)).toHaveCount(2);
  expect(await serials(page)).toEqual([before[0], before[2]]);
  await expect(page.locator("#nt-count")).toHaveText("3 sent");
});

test("a toast disappears on its own after about two seconds", async ({ page }) => {
  await sendN(page, 1);
  await expect(toasts(page)).toHaveCount(1);

  await page.clock.runFor(1500);
  await expect(toasts(page)).toHaveCount(1);

  await page.clock.runFor(600);
  await expect(toasts(page)).toHaveCount(0);
});

test("at most three toasts are shown; a fourth drops the oldest", async ({ page }) => {
  await sendN(page, 3);
  const before = await serials(page);
  expect(before).toHaveLength(3);

  await send(page).click();
  await expect(page.locator("#nt-count")).toHaveText("4 sent");

  await expect(toasts(page)).toHaveCount(3);
  const after = await serials(page);
  expect(after.slice(0, 2)).toEqual(before.slice(1));
  expect(before).not.toContain(after[2]);
});

test("the Notifications region is a polite live region", async ({ page }) => {
  await expect(region(page)).toHaveAttribute("aria-live", "polite");
});
