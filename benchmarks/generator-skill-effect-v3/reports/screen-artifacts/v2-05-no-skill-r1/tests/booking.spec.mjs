import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const slot = (page, time) => page.getByRole("list", { name: "Slots" }).getByRole("listitem").filter({ hasText: time });
const mine = (page) => page.getByRole("list", { name: "My bookings" });

test("books a free slot and lists it under My bookings", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();

  await page.getByRole("tab", { name: "Tue 13" }).click();
  await page.getByRole("button", { name: "Book 10:00 on Tue 13" }).click();

  await expect(slot(page, "10:00")).toContainText("Yours");
  await expect(mine(page).getByRole("listitem")).toHaveText(["Tue 13 10:00Cancel"]);
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
});

test("keeps the booking after a reload", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();
  await expect(slot(page, "09:00")).toContainText("Yours");

  await page.reload();
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
  await expect(slot(page, "09:00")).toContainText("Yours");
  await expect(mine(page)).toContainText("Mon 12 09:00");
});

test("cancelling a booking frees the slot so it can be booked again", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Book 11:00 on Mon 12" }).click();
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();

  await page.getByRole("button", { name: "Cancel Mon 12 11:00" }).click();
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
  await expect(slot(page, "11:00")).not.toContainText("Yours");
  await expect(page.getByRole("button", { name: "Book 11:00 on Mon 12" })).toBeVisible();

  // the cancellation reached the server, not just the UI
  await page.reload();
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Book 11:00 on Mon 12" })).toBeVisible();

  await page.getByRole("button", { name: "Book 11:00 on Mon 12" }).click();
  await expect(slot(page, "11:00")).toContainText("Yours");
  await expect(page.getByRole("heading", { name: "My bookings (2)" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
});

test("counts several bookings in the heading", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();
  await page.getByRole("button", { name: "Book 10:00 on Mon 12" }).click();
  await expect(page.getByRole("heading", { name: "My bookings (2)" })).toBeVisible();
  await expect(mine(page).getByRole("listitem")).toHaveCount(2);
});

test("shows a slot booked by someone else as Taken without a Book button", async ({ page, request }) => {
  await request.post("/api/dev/take", { data: { date: "Mon 12", time: "10:00" } });
  await page.goto("/");
  await expect(slot(page, "10:00")).toContainText("Taken");
  await expect(page.getByRole("button", { name: "Book 10:00 on Mon 12" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
});

test("reports a slot taken in the meantime and refreshes the list", async ({ page, request }) => {
  await page.goto("/");
  const book = page.getByRole("button", { name: "Book 09:00 on Mon 12" });
  await expect(book).toBeVisible();

  await request.post("/api/dev/take", { data: { date: "Mon 12", time: "09:00" } });
  await book.click();

  await expect(page.getByRole("alert")).toHaveText("That slot was just taken");
  await expect(slot(page, "09:00")).toContainText("Taken");
  await expect(slot(page, "09:00")).not.toContainText("Yours");
  await expect(page.getByRole("button", { name: "Book 09:00 on Mon 12" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
});
