import { expect, test } from "@playwright/test";

const slot = (page, time) => page.getByRole("list", { name: "Slots" }).getByRole("listitem").filter({ hasText: time });
const mine = (page) => page.getByRole("list", { name: "My bookings" });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(slot(page, "09:00")).toBeVisible();
});

test("books a slot and lists it under My bookings", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();

  await expect(slot(page, "09:00")).toContainText("Yours");
  await expect(mine(page).getByRole("listitem")).toHaveText(["Mon 12 09:00Cancel"]);
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
});

test("keeps the booking after a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Book 10:00 on Mon 12" }).click();
  await expect(slot(page, "10:00")).toContainText("Yours");

  await page.reload();
  await expect(slot(page, "10:00")).toContainText("Yours");
  await expect(mine(page).getByRole("listitem")).toHaveCount(1);
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
});

test("books on another day", async ({ page }) => {
  await page.getByRole("tab", { name: "Tue 13" }).click();
  await page.getByRole("button", { name: "Book 11:00 on Tue 13" }).click();

  await expect(slot(page, "11:00")).toContainText("Yours");
  await expect(mine(page)).toContainText("Tue 13 11:00");
  await page.getByRole("tab", { name: "Mon 12" }).click();
  await expect(slot(page, "11:00")).not.toContainText("Yours");
});

test("cancelling frees the slot so it can be booked again", async ({ page }) => {
  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();
  await expect(slot(page, "09:00")).toContainText("Yours");

  await page.getByRole("button", { name: "Cancel Mon 12 09:00" }).click();
  await expect(mine(page).getByRole("listitem")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
  await expect(slot(page, "09:00")).not.toContainText("Yours");

  await page.reload();
  await expect(slot(page, "09:00")).not.toContainText("Yours");
  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();
  await expect(slot(page, "09:00")).toContainText("Yours");
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
});

test("shows a conflict and refreshes when another visitor took the slot", async ({ page, request }) => {
  await request.post("/api/dev/take", { data: { date: "Mon 12", time: "10:00" } });
  // The page is stale: it still offers the slot.
  await expect(page.getByRole("button", { name: "Book 10:00 on Mon 12" })).toBeVisible();

  await page.getByRole("button", { name: "Book 10:00 on Mon 12" }).click();

  await expect(page.getByRole("alert")).toHaveText("That slot was just taken");
  await expect(slot(page, "10:00")).toContainText("Taken");
  await expect(page.getByRole("button", { name: "Book 10:00 on Mon 12" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
});
