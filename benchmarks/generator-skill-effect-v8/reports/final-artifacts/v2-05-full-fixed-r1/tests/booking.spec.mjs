import { expect, test } from "@playwright/test";

const slots = {
  first: { date: "Mon 12", time: "09:00" },
  second: { date: "Mon 12", time: "10:00" },
  third: { date: "Mon 12", time: "11:00" },
};

const slotItem = (page, time) => {
  return page.getByRole("list", { name: "Slots", exact: true }).getByRole("listitem").filter({ hasText: new RegExp(`^${time}`) });
};

const bookingItem = (page, date, time) => {
  return page.getByRole("list", { name: "My bookings", exact: true }).getByRole("listitem").filter({ hasText: `${date} ${time}` });
};

const bookButton = (page, { date, time }) => {
  return page.getByRole("button", { name: `Book ${time} on ${date}`, exact: true });
};

const cancelButton = (page, { date, time }) => {
  return page.getByRole("button", { name: `Cancel ${date} ${time}`, exact: true });
};

const bookingRequestFor = (page, { date, time }) =>
  page.waitForRequest((request) => {
    if (request.method() !== "POST" || new URL(request.url()).pathname !== "/api/bookings") return false;
    return request.postDataJSON().date === date && request.postDataJSON().time === time;
  });

test.beforeEach(async ({ page, request }) => {
  await expect(await request.post("/api/reset")).toBeOK();
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Appointments", exact: true })).toBeVisible();
});

test("books a free slot and keeps it after reload", async ({ page }) => {
  const slot = slots.first;
  const bookingRequest = bookingRequestFor(page, slot);

  await bookButton(page, slot).click();
  await bookingRequest;

  await expect(page.getByRole("heading", { name: "My bookings (1)", exact: true })).toBeVisible();
  await expect(bookingItem(page, slot.date, slot.time)).toBeVisible();
  await expect(slotItem(page, slot.time)).toContainText(/09:00.*Yours/);

  await page.reload();

  await expect(page.getByRole("heading", { name: "My bookings (1)", exact: true })).toBeVisible();
  await expect(bookingItem(page, slot.date, slot.time)).toBeVisible();
  await expect(slotItem(page, slot.time)).toContainText(/09:00.*Yours/);
});

test("cancels a booking and can book the freed slot again", async ({ page }) => {
  const slot = slots.second;
  const firstBookingRequest = bookingRequestFor(page, slot);
  await bookButton(page, slot).click();
  await firstBookingRequest;
  await expect(page.getByRole("heading", { name: "My bookings (1)", exact: true })).toBeVisible();

  const cancelRequest = page.waitForRequest((request) => {
    return request.method() === "DELETE" && /\/api\/bookings\/\d+$/.test(new URL(request.url()).pathname);
  });
  await cancelButton(page, slot).click();
  await cancelRequest;

  await expect(page.getByRole("heading", { name: "My bookings (0)", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "My bookings (0)", exact: true })).toBeVisible();
  await expect(bookButton(page, slot)).toBeVisible();

  const secondBookingRequest = bookingRequestFor(page, slot);
  await bookButton(page, slot).click();
  await secondBookingRequest;

  await expect(page.getByRole("heading", { name: "My bookings (1)", exact: true })).toBeVisible();
  await expect(bookingItem(page, slot.date, slot.time)).toBeVisible();
  await expect(slotItem(page, slot.time)).toContainText(/10:00.*Yours/);
});

test("shows when a slot was just taken by another visitor", async ({ page }) => {
  const slot = slots.third;
  await expect(bookButton(page, slot)).toBeVisible();
  await expect(await page.request.post("/api/dev/take", { data: slot })).toBeOK();

  const rejectedBooking = page.waitForResponse((response) => {
    return response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/bookings" &&
      response.status() === 409;
  });
  await bookButton(page, slot).click();
  await rejectedBooking;

  await expect(page.getByRole("alert")).toHaveText("That slot was just taken");
  await expect(slotItem(page, slot.time)).toContainText(/11:00.*Taken/);
  await expect(page.getByRole("heading", { name: "My bookings (0)", exact: true })).toBeVisible();
});
