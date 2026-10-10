import { expect, test } from "@playwright/test";

const resetAppointments = async (request) => {
  const response = await request.post("/api/reset");
  expect(response.ok()).toBeTruthy();
};

const slotItem = (page, time) =>
  page.getByRole("list", { name: "Slots", exact: true }).getByRole("listitem").filter({ hasText: time });

test.beforeEach(async ({ request }) => {
  await resetAppointments(request);
});

test("books a slot, keeps it after reload, and can cancel then rebook it", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Appointments", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "My bookings (0)", exact: true })).toBeVisible();

  const bookingRequest = page.waitForRequest(
    (request) => request.method() === "POST" && request.url().endsWith("/api/bookings"),
  );
  await page.getByRole("button", { name: "Book 10:00 on Mon 12", exact: true }).click();
  const request = await bookingRequest;
  expect(request.postDataJSON()).toEqual({ date: "Mon 12", time: "10:00" });

  await expect(page.getByRole("heading", { name: "My bookings (1)", exact: true })).toBeVisible();
  await expect(slotItem(page, "10:00")).toContainText("10:00 — Yours");
  await expect(page.getByRole("list", { name: "My bookings", exact: true })).toContainText("Mon 12 10:00");

  await page.reload();

  await expect(page.getByRole("heading", { name: "My bookings (1)", exact: true })).toBeVisible();
  await expect(slotItem(page, "10:00")).toContainText("10:00 — Yours");

  const cancelRequest = page.waitForRequest(
    (request) => request.method() === "DELETE" && /\/api\/bookings\/\d+$/.test(request.url()),
  );
  await page.getByRole("button", { name: "Cancel Mon 12 10:00", exact: true }).click();
  await cancelRequest;

  await expect(page.getByRole("heading", { name: "My bookings (0)", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Book 10:00 on Mon 12", exact: true })).toBeVisible();

  await page.reload();

  await expect(page.getByRole("heading", { name: "My bookings (0)", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Book 10:00 on Mon 12", exact: true })).toBeVisible();

  const rebookingRequest = page.waitForRequest(
    (request) => request.method() === "POST" && request.url().endsWith("/api/bookings"),
  );
  const rebookingResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/api/bookings") &&
      response.status() === 201,
  );
  await page.getByRole("button", { name: "Book 10:00 on Mon 12", exact: true }).click();
  await rebookingRequest;
  await rebookingResponse;

  await expect(page.getByRole("heading", { name: "My bookings (1)", exact: true })).toBeVisible();
  await expect(slotItem(page, "10:00")).toContainText("10:00 — Yours");

  await page.reload();

  await expect(page.getByRole("heading", { name: "My bookings (1)", exact: true })).toBeVisible();
  await expect(slotItem(page, "10:00")).toContainText("10:00 — Yours");
});

test("shows a taken message and refreshes the slot when someone else books first", async ({ page, request }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Appointments", exact: true })).toBeVisible();
  const devTake = await request.post("/api/dev/take", { data: { date: "Wed 14", time: "09:00" } });
  expect(devTake.ok()).toBeTruthy();

  await page.getByRole("tab", { name: "Wed 14", exact: true }).click();
  await expect(page.getByRole("button", { name: "Book 09:00 on Wed 14", exact: true })).toBeVisible();

  const rejectedBooking = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/api/bookings") &&
      response.status() === 409,
  );
  await page.getByRole("button", { name: "Book 09:00 on Wed 14", exact: true }).click();
  await rejectedBooking;

  await expect(page.getByRole("alert")).toHaveText("That slot was just taken");
  await expect(slotItem(page, "09:00")).toContainText("09:00 — Taken");
  await expect(page.getByRole("heading", { name: "My bookings (0)", exact: true })).toBeVisible();
});
