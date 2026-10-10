import { expect, test } from "@playwright/test";

const region = (page) => page.getByRole("region", { name: "Notifications" });
const toasts = (page) => region(page).getByText("Test notification sent");
const send = (page) => page.getByRole("button", { name: "Send test notification" }).click();

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("sending shows a toast, bumps the counter, and the toast auto-dismisses", async ({ page }) => {
  await send(page);
  await expect(toasts(page)).toHaveCount(1);
  await expect(page.getByText("1 sent")).toBeVisible();
  await expect(toasts(page)).toHaveCount(0, { timeout: 4000 });
});

test("dismiss removes exactly its own toast", async ({ page }) => {
  await send(page);
  await send(page);
  await send(page);
  await expect(toasts(page)).toHaveCount(3);
  const serialsBefore = await region(page).locator(".toast, [data-serial]").evaluateAll((nodes) => nodes.map((n) => n.dataset.serial));
  await region(page).getByRole("button", { name: "Dismiss notification" }).nth(1).click();
  const serialsAfter = await region(page).locator("[data-serial]").evaluateAll((nodes) => nodes.map((n) => n.dataset.serial));
  expect(serialsAfter).toEqual([serialsBefore[0], serialsBefore[2]]);
});

test("at most three toasts are shown", async ({ page }) => {
  for (let i = 0; i < 4; i += 1) {
    await send(page);
    await expect(page.getByText(`${i + 1} sent`)).toBeVisible();
  }
  const serials = await region(page).locator("[data-serial]").evaluateAll((nodes) => nodes.map((n) => n.dataset.serial));
  expect(serials).toEqual(["2", "3", "4"]);
  await expect(toasts(page)).toHaveCount(3);
});

test("the region is a polite live region", async ({ page }) => {
  await expect(region(page)).toHaveAttribute("aria-live", "polite");
});
