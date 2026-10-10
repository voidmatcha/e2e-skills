import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("books, persists, cancels, and rebooks a free slot", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();

  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();

  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
  await expect(page.getByLabel("Slots").getByText("09:00 — Yours")).toBeVisible();
  await expect(page.getByLabel("My bookings").getByText("Mon 12 09:00")).toBeVisible();

  await page.reload();

  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
  await expect(page.getByLabel("Slots").getByText("09:00 — Yours")).toBeVisible();
  await expect(page.getByLabel("My bookings").getByText("Mon 12 09:00")).toBeVisible();

  await page.getByRole("button", { name: "Cancel Mon 12 09:00" }).click();

  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
  await expect(page.getByLabel("Slots").getByText("09:00 — Yours")).toBeHidden();
  await expect(page.getByRole("button", { name: "Book 09:00 on Mon 12" })).toBeVisible();

  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();

  await expect(page.getByRole("heading", { name: "My bookings (1)" })).toBeVisible();
  await expect(page.getByLabel("Slots").getByText("09:00 — Yours")).toBeVisible();
});

test("refreshes the slot list when another visitor just took the slot", async ({ page, request }) => {
  await page.goto("/");

  await expect(page.getByRole("button", { name: "Book 10:00 on Mon 12" })).toBeVisible();

  await request.post("/api/dev/take", {
    data: { date: "Mon 12", time: "10:00" },
  });
  await page.getByRole("button", { name: "Book 10:00 on Mon 12" }).click();

  await expect(page.getByRole("alert")).toHaveText("That slot was just taken");
  await expect(page.getByLabel("Slots").getByText("10:00 — Taken")).toBeVisible();
  await expect(page.getByRole("button", { name: "Book 10:00 on Mon 12" })).toBeHidden();
  await expect(page.getByRole("heading", { name: "My bookings (0)" })).toBeVisible();
});
