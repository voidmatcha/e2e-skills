import { expect, test } from "@playwright/test";

const slots = (page) => page.getByRole("list", { name: "Slots" });
const mine = (page) => page.getByRole("list", { name: "My bookings" });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(slots(page).getByRole("listitem")).toHaveCount(3);
});

test("books a free slot and shows it under My bookings", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
  await page.getByRole("tab", { name: "Tue 13" }).click();
  await page.getByRole("button", { name: "Book 10:00 on Tue 13" }).click();

  await expect(slots(page).getByRole("listitem").filter({ hasText: "10:00" })).toContainText("Yours");
  await expect(mine(page).getByRole("listitem")).toHaveText(/Tue 13 10:00/);
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
});

test("a booking stays booked after reload", async ({ page }) => {
  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
  await expect(mine(page).getByRole("listitem")).toHaveText(/Mon 12 09:00/);
  await expect(slots(page).getByRole("listitem").filter({ hasText: "09:00" })).toContainText("Yours");
});

test("cancelling frees the slot so it can be booked again", async ({ page }) => {
  await page.getByRole("button", { name: "Book 11:00 on Mon 12" }).click();
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();

  await page.getByRole("button", { name: "Cancel Mon 12 11:00" }).click();
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
  await expect(mine(page).getByRole("listitem")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Book 11:00 on Mon 12" })).toBeVisible();

  // the server freed it too, not just the UI
  await page.reload();
  await page.getByRole("button", { name: "Book 11:00 on Mon 12" }).click();
  await expect(slots(page).getByRole("listitem").filter({ hasText: "11:00" })).toContainText("Yours");
  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
});

test("heading counts several bookings", async ({ page }) => {
  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();
  await page.getByRole("button", { name: "Book 10:00 on Mon 12" }).click();
  await expect(page.getByRole("heading", { name: "My bookings (2)" })).toBeVisible();
  await expect(mine(page).getByRole("listitem")).toHaveCount(2);
});

test("booking a slot taken by someone else shows an error and refreshes the list", async ({ page, request }) => {
  const open = page.getByRole("button", { name: "Book 10:00 on Mon 12" });
  await expect(open).toBeVisible();
  const res = await request.post("/api/dev/take", { data: { date: "Mon 12", time: "10:00" } });
  expect(res.ok()).toBe(true);

  await open.click();
  await expect(page.getByRole("alert")).toHaveText("That slot was just taken");
  await expect(slots(page).getByRole("listitem").filter({ hasText: "10:00" })).toContainText("Taken");
  await expect(page.getByRole("button", { name: "Book 10:00 on Mon 12" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
});
