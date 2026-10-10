import { expect, test } from "@playwright/test";

const seatButton = (page, seat) => page.getByRole("button", { name: `Seat ${seat}`, exact: true });

test.beforeEach(async ({ page }) => {
  const reset = await page.request.post("/api/reset");
  expect(reset.status()).toBe(200);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Pick your seats", exact: true })).toBeVisible();
});

test("selects and deselects free seats while updating the legend", async ({ page }) => {
  await expect(page.getByRole("button")).toHaveCount(13);
  await expect(seatButton(page, "A1")).toBeDisabled();
  await expect(seatButton(page, "A2")).toBeVisible();
  await expect(seatButton(page, "A3")).toBeVisible();
  await expect(seatButton(page, "A4")).toBeVisible();
  await expect(seatButton(page, "B1")).toBeVisible();
  await expect(seatButton(page, "B2")).toBeVisible();
  await expect(seatButton(page, "B3")).toBeDisabled();
  await expect(seatButton(page, "B4")).toBeVisible();
  await expect(seatButton(page, "C1")).toBeVisible();
  await expect(seatButton(page, "C2")).toBeVisible();
  await expect(seatButton(page, "C3")).toBeVisible();
  await expect(seatButton(page, "C4")).toBeDisabled();
  await expect(page.getByText("Selected 0 · Available 9 · Taken 3")).toBeVisible();

  await seatButton(page, "A2").click();
  await expect(seatButton(page, "A2")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("Selected: A2")).toBeVisible();
  await expect(page.getByText("Selected 1 · Available 8 · Taken 3")).toBeVisible();

  await seatButton(page, "B1").click();
  await expect(seatButton(page, "B1")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("Selected: A2, B1")).toBeVisible();
  await expect(page.getByText("Selected 2 · Available 7 · Taken 3")).toBeVisible();

  await seatButton(page, "A2").click();
  await expect(seatButton(page, "A2")).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByText("Selected: B1")).toBeVisible();
  await expect(page.getByText("Selected 1 · Available 8 · Taken 3")).toBeVisible();
});

test("keeps the fifth selected seat out of the selection", async ({ page }) => {
  await seatButton(page, "A2").click();
  await seatButton(page, "A3").click();
  await seatButton(page, "A4").click();
  await seatButton(page, "B1").click();
  await expect(page.getByText("Selected 4 · Available 5 · Taken 3")).toBeVisible();

  await seatButton(page, "B2").click();
  await expect(page.getByText("You can pick up to 4 seats")).toBeVisible();
  await expect(seatButton(page, "B2")).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByText("Selected: A2, A3, A4, B1")).toBeVisible();
  await expect(page.getByText("Selected 4 · Available 5 · Taken 3")).toBeVisible();
});

test("reserves selected seats and keeps them taken after reload", async ({ page }) => {
  await seatButton(page, "A2").click();
  await seatButton(page, "B1").click();
  await expect(page.getByText("Selected: A2, B1")).toBeVisible();

  const reservationRequest = page.waitForRequest((request) => {
    return request.method() === "POST" && new URL(request.url()).pathname === "/api/reservations";
  });
  await page.getByRole("button", { name: "Reserve", exact: true }).click();
  expect((await reservationRequest).postDataJSON()).toEqual({ seats: ["A2", "B1"] });

  await expect(page.getByText("Reserved A2, B1")).toBeVisible();
  await expect(page.getByText("Selected: none")).toBeVisible();
  await expect(page.getByText("Selected 0 · Available 7 · Taken 5")).toBeVisible();
  await expect(seatButton(page, "A2")).toBeDisabled();
  await expect(seatButton(page, "B1")).toBeDisabled();

  await page.reload();
  await expect(page.getByText("Selected 0 · Available 7 · Taken 5")).toBeVisible();
  await expect(seatButton(page, "A2")).toBeDisabled();
  await expect(seatButton(page, "B1")).toBeDisabled();
});
