import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.clock.install();
  await page.goto("/");
});

const sendButton = (page) => page.getByRole("button", { name: "Send test notification" });
const region = (page) => page.getByRole("region", { name: "Notifications" });
const toasts = (page) => region(page).locator("[data-serial]");

async function send(page, times = 1) {
  for (let i = 0; i < times; i++) {
    const count = Number((await page.locator("#nt-count").textContent()).split(" ")[0]);
    await sendButton(page).click();
    await expect(page.locator("#nt-count")).toHaveText(`${count + 1} sent`);
  }
}

test("sending shows a toast in the Notifications region and bumps the counter", async ({ page }) => {
  await expect(page.getByText("0 sent")).toBeVisible();
  await sendButton(page).click();
  await expect(region(page).getByText("Test notification sent")).toBeVisible();
  await expect(page.getByText("1 sent")).toBeVisible();
  await sendButton(page).click();
  await expect(page.getByText("2 sent")).toBeVisible();
});

test("Dismiss notification removes only its own toast", async ({ page }) => {
  await send(page, 3);
  await expect(toasts(page)).toHaveCount(3);
  const serials = await toasts(page).evaluateAll((els) => els.map((e) => e.dataset.serial));

  await toasts(page).nth(1).getByRole("button", { name: "Dismiss notification" }).click();

  await expect(toasts(page)).toHaveCount(2);
  await expect(toasts(page).evaluateAll((els) => els.map((e) => e.dataset.serial))).resolves.toEqual([
    serials[0],
    serials[2],
  ]);
});

test("a toast disappears on its own after about two seconds", async ({ page }) => {
  await sendButton(page).click();
  await expect(toasts(page)).toHaveCount(1);
  await page.clock.runFor(1500);
  await expect(toasts(page)).toHaveCount(1);
  await page.clock.runFor(700);
  await expect(toasts(page)).toHaveCount(0);
});

test("a fourth toast drops the oldest", async ({ page }) => {
  await send(page, 3);
  const before = await toasts(page).evaluateAll((els) => els.map((e) => e.dataset.serial));
  expect(before).toHaveLength(3);

  await send(page);

  await expect(toasts(page)).toHaveCount(3);
  const after = await toasts(page).evaluateAll((els) => els.map((e) => e.dataset.serial));
  expect(after.slice(0, 2)).toEqual(before.slice(1));
  expect(after).not.toContain(before[0]);
  await expect(page.getByText("4 sent")).toBeVisible();
});

test("the Notifications region is a polite live region", async ({ page }) => {
  await expect(region(page)).toHaveAttribute("aria-live", "polite");
});
