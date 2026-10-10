import { expect, test } from "@playwright/test";

const slotItem = (page, time) =>
  page.getByRole("list", { name: "Slots" }).getByRole("listitem").filter({ hasText: time });

const myBookingItem = (page, booking) =>
  page.getByRole("list", { name: "My bookings" }).getByRole("listitem").filter({ hasText: booking });

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("books, persists, cancels, and rebooks a free slot", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();

  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();

  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
  await expect(myBookingItem(page, "Mon 12 09:00")).toBeVisible();
  await expect(slotItem(page, "09:00")).toContainText("Yours");
  await expect(page.getByRole("button", { name: "Book 09:00 on Mon 12" })).toHaveCount(0);

  await page.reload();

  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
  await expect(myBookingItem(page, "Mon 12 09:00")).toBeVisible();
  await expect(slotItem(page, "09:00")).toContainText("Yours");

  await page.getByRole("button", { name: "Cancel Mon 12 09:00" }).click();

  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
  await expect(myBookingItem(page, "Mon 12 09:00")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Book 09:00 on Mon 12" })).toBeVisible();
  await expect(slotItem(page, "09:00")).not.toContainText("Yours");

  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();

  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
  await expect(myBookingItem(page, "Mon 12 09:00")).toBeVisible();
  await expect(slotItem(page, "09:00")).toContainText("Yours");
});

test("shows a stale slot conflict and refreshes the slot list", async ({ page, request }) => {
  await page.goto("/");

  await expect(page.getByRole("button", { name: "Book 10:00 on Mon 12" })).toBeVisible();
  await request.post("/api/dev/take", { data: { date: "Mon 12", time: "10:00" } });

  await page.getByRole("button", { name: "Book 10:00 on Mon 12" }).click();

  await expect(page.getByRole("alert")).toHaveText("That slot was just taken");
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
  await expect(slotItem(page, "10:00")).toContainText("Taken");
  await expect(page.getByRole("button", { name: "Book 10:00 on Mon 12" })).toHaveCount(0);
});
