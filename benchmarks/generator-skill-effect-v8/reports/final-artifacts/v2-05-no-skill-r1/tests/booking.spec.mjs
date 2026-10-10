import { expect, test } from "@playwright/test";

const day = "Mon 12";
const time = "09:00";

const slot = (page, value = time) =>
  page.getByRole("list", { name: "Slots" }).getByRole("listitem").filter({ hasText: value });
const bookButton = (page, value = time, date = day) =>
  page.getByRole("button", { name: `Book ${value} on ${date}` });
const myBookingsHeading = (page, count) =>
  page.getByRole("heading", { name: `My bookings (${count})` });

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("books, persists, cancels, and rebooks a slot", async ({ page }) => {
  await page.goto("/");

  await expect(myBookingsHeading(page, 0)).toBeVisible();
  await bookButton(page).click();

  await expect(myBookingsHeading(page, 1)).toBeVisible();
  await expect(slot(page)).toContainText("09:00 — Yours");
  await expect(page.getByRole("list", { name: "My bookings" })).toContainText("Mon 12 09:00");

  await page.reload();

  await expect(myBookingsHeading(page, 1)).toBeVisible();
  await expect(slot(page)).toContainText("09:00 — Yours");
  await expect(page.getByRole("list", { name: "My bookings" })).toContainText("Mon 12 09:00");

  await page.getByRole("button", { name: "Cancel Mon 12 09:00" }).click();

  await expect(myBookingsHeading(page, 0)).toBeVisible();
  await expect(slot(page)).toHaveText("09:00Book");
  await expect(bookButton(page)).toBeVisible();

  await bookButton(page).click();

  await expect(myBookingsHeading(page, 1)).toBeVisible();
  await expect(slot(page)).toContainText("09:00 — Yours");
});

test("shows a taken message and refreshes when another visitor gets the slot first", async ({ page, request }) => {
  await page.goto("/");

  await request.post("/api/dev/take", { data: { date: day, time } });
  await bookButton(page).click();

  await expect(page.getByRole("alert")).toHaveText("That slot was just taken");
  await expect(myBookingsHeading(page, 0)).toBeVisible();
  await expect(slot(page)).toHaveText("09:00 — Taken");
  await expect(bookButton(page)).toBeHidden();
});
