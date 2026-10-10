import { expect, test } from "@playwright/test";

const seatButton = (page, seat) => page.getByRole("button", { name: `Seat ${seat}`, exact: true });
const seatLabels = ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "C1", "C2", "C3", "C4"];

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("shows the seeded seat inventory", async ({ page }) => {
  for (const seat of seatLabels) {
    await expect(seatButton(page, seat)).toBeVisible();
  }
  await expect(page.getByText("Selected 0 · Available 9 · Taken 3")).toBeVisible();
  await expect(page.getByText("Selected: none")).toBeVisible();
  await expect(seatButton(page, "A1")).toBeDisabled();
  await expect(seatButton(page, "B3")).toBeDisabled();
  await expect(seatButton(page, "C4")).toBeDisabled();
});

test("selects and deselects available seats", async ({ page }) => {
  const seatA2 = seatButton(page, "A2");
  const seatB1 = seatButton(page, "B1");

  await seatA2.click();
  await seatB1.click();

  await expect(seatA2).toHaveAttribute("aria-pressed", "true");
  await expect(seatB1).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("Selected: A2, B1")).toBeVisible();
  await expect(page.getByText("Selected 2 · Available 7 · Taken 3")).toBeVisible();

  await seatA2.click();

  await expect(seatA2).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByText("Selected: B1")).toBeVisible();
  await expect(page.getByText("Selected 1 · Available 8 · Taken 3")).toBeVisible();
});

test("prevents selecting a fifth seat", async ({ page }) => {
  for (const seat of ["A2", "B1", "A3", "A4"]) {
    await seatButton(page, seat).click();
  }

  const fifthSeat = seatButton(page, "B2");
  await fifthSeat.click();

  await expect(page.getByText("You can pick up to 4 seats")).toBeVisible();
  await expect(fifthSeat).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByText("Selected: A2, B1, A3, A4")).toBeVisible();
  await expect(page.getByText("Selected 4 · Available 5 · Taken 3")).toBeVisible();
});

test("reserves selected seats and persists them after reload", async ({ page }) => {
  await seatButton(page, "A2").click();
  await seatButton(page, "B1").click();

  const reservationRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === "POST" && url.pathname === "/api/reservations";
  });

  await page.getByRole("button", { name: "Reserve", exact: true }).click();

  const request = await reservationRequest;
  expect(request.postDataJSON()).toEqual({ seats: ["A2", "B1"] });
  await expect(page.getByText("Reserved A2, B1")).toBeVisible();
  await expect(page.getByText("Selected: none")).toBeVisible();
  await expect(page.getByText("Selected 0 · Available 7 · Taken 5")).toBeVisible();
  await expect(seatButton(page, "A2")).toBeDisabled();
  await expect(seatButton(page, "B1")).toBeDisabled();

  await page.reload();

  await expect(seatButton(page, "A2")).toBeDisabled();
  await expect(seatButton(page, "B1")).toBeDisabled();
  await expect(page.getByText("Selected 0 · Available 7 · Taken 5")).toBeVisible();
});
