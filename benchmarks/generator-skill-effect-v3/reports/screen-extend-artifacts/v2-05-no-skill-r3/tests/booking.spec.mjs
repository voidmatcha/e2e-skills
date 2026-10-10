import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("tab", { name: "Mon 12" })).toBeVisible();
});

const slot = (page, time) => page.getByRole("list", { name: "Slots" }).getByRole("listitem").filter({ hasText: time });
const mine = (page) => page.getByRole("list", { name: "My bookings" });

test("books a slot, shows it under My bookings and keeps it after reload", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
  await page.getByRole("tab", { name: "Tue 13" }).click();
  await page.getByRole("button", { name: "Book 10:00 on Tue 13" }).click();

  await expect(slot(page, "10:00")).toContainText("Yours");
  await expect(mine(page).getByRole("listitem")).toHaveText(/Tue 13 10:00/);
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();

  await page.reload();
  await page.getByRole("tab", { name: "Tue 13" }).click();
  await expect(slot(page, "10:00")).toContainText("Yours");
  await expect(mine(page).getByRole("listitem")).toHaveText(/Tue 13 10:00/);
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
});

test("cancelling a booking frees the slot so it can be booked again", async ({ page }) => {
  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();

  await page.getByRole("button", { name: "Cancel Mon 12 09:00" }).click();
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
  await expect(mine(page).getByRole("listitem")).toHaveCount(0);
  await expect(slot(page, "09:00")).not.toContainText("Yours");

  await page.reload();
  await expect(page.getByRole("button", { name: "Book 09:00 on Mon 12" })).toBeVisible();
  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();
  await expect(slot(page, "09:00")).toContainText("Yours");
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
});

test("counts several bookings in the My bookings heading", async ({ page }) => {
  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();
  await page.getByRole("button", { name: "Book 11:00 on Mon 12" }).click();
  await expect(page.getByRole("heading", { name: "My bookings (2)" })).toBeVisible();
  await expect(mine(page).getByRole("listitem")).toHaveCount(2);
});

test("shows a conflict message and refreshes the list when the slot was just taken", async ({ page }) => {
  const taken = await page.request.post("/api/dev/take", { data: { date: "Mon 12", time: "10:00" } });
  expect(taken.ok()).toBeTruthy();

  // The page still shows the slot as free until the booking attempt.
  await expect(slot(page, "10:00")).not.toContainText("Taken");
  await page.getByRole("button", { name: "Book 10:00 on Mon 12" }).click();

  await expect(page.getByRole("alert")).toHaveText("That slot was just taken");
  await expect(slot(page, "10:00")).toContainText("Taken");
  await expect(page.getByRole("button", { name: "Book 10:00 on Mon 12" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
});
