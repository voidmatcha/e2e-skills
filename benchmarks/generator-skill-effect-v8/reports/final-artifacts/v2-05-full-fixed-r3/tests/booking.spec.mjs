import { expect, test } from "@playwright/test";

const slotItem = (page, date, time) =>
  page
    .getByRole("list", { name: "Slots" })
    .getByRole("listitem")
    .filter({ hasText: new RegExp(`^${time}`) });

const myBookingItem = (page, date, time) =>
  page
    .getByRole("list", { name: "My bookings" })
    .getByRole("listitem")
    .filter({ hasText: `${date} ${time}` });

async function openAppointments(page) {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "My bookings (0)", exact: true })).toBeVisible();
}

async function bookSlot(page, date, time) {
  const bookingRequest = page.waitForRequest((request) => {
    if (request.method() !== "POST" || !request.url().endsWith("/api/bookings")) return false;
    const body = request.postDataJSON();
    return body.date === date && body.time === time;
  });

  const bookingResponse = page.waitForResponse((response) =>
    response.request().method() === "POST" && response.url().endsWith("/api/bookings")
  );

  await slotItem(page, date, time).getByRole("button", { name: `Book ${time} on ${date}` }).click();
  await bookingRequest;
  expect((await bookingResponse).status()).toBe(201);
}

test("books a free slot and keeps it after reload", async ({ page }) => {
  await openAppointments(page);

  await bookSlot(page, "Mon 12", "09:00");

  await expect(slotItem(page, "Mon 12", "09:00")).toContainText("09:00 — Yours");
  await expect(myBookingItem(page, "Mon 12", "09:00")).toBeVisible();
  await expect(page.getByRole("heading", { name: "My bookings (1)", exact: true })).toBeVisible();

  await page.reload();

  await expect(slotItem(page, "Mon 12", "09:00")).toContainText("09:00 — Yours");
  await expect(myBookingItem(page, "Mon 12", "09:00")).toBeVisible();
  await expect(page.getByRole("heading", { name: "My bookings (1)", exact: true })).toBeVisible();
});

test("cancelling a booking frees the slot so it can be booked again", async ({ page }) => {
  await openAppointments(page);
  await bookSlot(page, "Mon 12", "10:00");

  const cancelRequest = page.waitForRequest((request) =>
    request.method() === "DELETE" && /\/api\/bookings\/\d+$/.test(request.url())
  );

  await myBookingItem(page, "Mon 12", "10:00")
    .getByRole("button", { name: "Cancel Mon 12 10:00" })
    .click();
  await cancelRequest;

  await expect(page.getByRole("heading", { name: "My bookings (0)", exact: true })).toBeVisible();
  await expect(slotItem(page, "Mon 12", "10:00")).toContainText("10:00");
  await expect(slotItem(page, "Mon 12", "10:00")).not.toContainText("Yours");
  await expect(slotItem(page, "Mon 12", "10:00").getByRole("button", { name: "Book 10:00 on Mon 12" })).toBeVisible();

  await bookSlot(page, "Mon 12", "10:00");

  await expect(slotItem(page, "Mon 12", "10:00")).toContainText("10:00 — Yours");
  await expect(page.getByRole("heading", { name: "My bookings (1)", exact: true })).toBeVisible();
});

test("refreshes the slot list when another visitor takes the slot first", async ({ page }) => {
  await openAppointments(page);

  await page.request.post("/api/dev/take", {
    data: { date: "Mon 12", time: "11:00" },
  });

  const bookingRequest = page.waitForRequest((request) => {
    if (request.method() !== "POST" || !request.url().endsWith("/api/bookings")) return false;
    const body = request.postDataJSON();
    return body.date === "Mon 12" && body.time === "11:00";
  });

  await slotItem(page, "Mon 12", "11:00").getByRole("button", { name: "Book 11:00 on Mon 12" }).click();
  await bookingRequest;

  await expect(page.getByRole("alert")).toHaveText("That slot was just taken");
  await expect(slotItem(page, "Mon 12", "11:00")).toContainText("11:00 — Taken");
  await expect(page.getByRole("heading", { name: "My bookings (0)", exact: true })).toBeVisible();
});
