import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Book 09:00 on Mon 12" })).toBeVisible();
});

test("books a slot and lists it under My bookings", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
  await page.getByRole("button", { name: "Book 10:00 on Mon 12" }).click();

  await expect(page.getByRole("list", { name: "Slots" }).getByText("10:00 — Yours")).toBeVisible();
  await expect(page.getByRole("list", { name: "My bookings" }).getByText("Mon 12 10:00")).toBeVisible();
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Book 10:00 on Mon 12" })).toHaveCount(0);
});

test("keeps the booking after a reload", async ({ page }) => {
  await page.getByRole("tab", { name: "Tue 13" }).click();
  await page.getByRole("button", { name: "Book 11:00 on Tue 13" }).click();
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
  await expect(page.getByRole("list", { name: "My bookings" }).getByText("Tue 13 11:00")).toBeVisible();
  await page.getByRole("tab", { name: "Tue 13" }).click();
  await expect(page.getByRole("list", { name: "Slots" }).getByText("11:00 — Yours")).toBeVisible();
});

test("counts several bookings across days", async ({ page }) => {
  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
  await page.getByRole("tab", { name: "Wed 14" }).click();
  await page.getByRole("button", { name: "Book 10:00 on Wed 14" }).click();
  await expect(page.getByRole("heading", { name: "My bookings (2)" })).toBeVisible();
});

test("cancelling a booking frees the slot so it can be booked again", async ({ page }) => {
  const slots = page.getByRole("list", { name: "Slots" });
  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();

  await page.getByRole("button", { name: "Cancel Mon 12 09:00" }).click();
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
  await expect(slots.getByText("Yours")).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();
  await expect(slots.getByText("09:00 — Yours")).toBeVisible();
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
});

test("shows an error and refreshes when another visitor took the slot", async ({ page, request }) => {
  const slots = page.getByRole("list", { name: "Slots" });
  await request.post("/api/dev/take", { data: { date: "Mon 12", time: "11:00" } });
  // the page still shows the slot as free until it is refreshed
  await expect(page.getByRole("button", { name: "Book 11:00 on Mon 12" })).toBeVisible();

  await page.getByRole("button", { name: "Book 11:00 on Mon 12" }).click();

  await expect(page.getByRole("alert")).toHaveText("That slot was just taken");
  await expect(slots.getByText("11:00 — Taken")).toBeVisible();
  await expect(page.getByRole("button", { name: "Book 11:00 on Mon 12" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
});
