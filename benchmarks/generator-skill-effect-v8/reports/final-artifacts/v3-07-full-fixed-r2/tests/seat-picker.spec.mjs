import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("Selected 0 · Available 9 · Taken 3")).toBeVisible();
});

const seatButton = (page, seat) => page.getByRole("button", { name: `Seat ${seat}`, exact: true });

test("selects and deselects available seats", async ({ page }) => {
  const seatA2 = seatButton(page, "A2");
  const seatB1 = seatButton(page, "B1");

  await seatA2.click();
  await seatB1.click();

  await expect(page.getByText("Selected: A2, B1")).toBeVisible();
  await expect(seatA2).toHaveAttribute("aria-pressed", "true");
  await expect(seatB1).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("Selected 2 · Available 7 · Taken 3")).toBeVisible();

  await seatA2.click();

  await expect(page.getByText("Selected: B1")).toBeVisible();
  await expect(seatA2).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByText("Selected 1 · Available 8 · Taken 3")).toBeVisible();
});

test("limits selection to four seats", async ({ page }) => {
  for (const seat of ["A2", "B1", "B2", "C1"]) {
    await seatButton(page, seat).click();
  }

  await seatButton(page, "C2").click();

  await expect(page.getByText("You can pick up to 4 seats")).toBeVisible();
  await expect(page.getByText("Selected: A2, B1, B2, C1")).toBeVisible();
  await expect(seatButton(page, "C2")).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByText("Selected 4 · Available 5 · Taken 3")).toBeVisible();
});

test("reserves selected seats and keeps them taken after reload", async ({ page }) => {
  const seatA2 = seatButton(page, "A2");
  const seatB1 = seatButton(page, "B1");

  await seatA2.click();
  await seatB1.click();

  const reservation = page.waitForResponse((response) =>
    response.url().endsWith("/api/reservations") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Reserve", exact: true }).click();
  const response = await reservation;

  expect(response.status()).toBe(201);
  expect(response.request().postDataJSON()).toEqual({ seats: ["A2", "B1"] });
  await expect(page.getByText("Reserved A2, B1")).toBeVisible();
  await expect(page.getByText("Selected: none")).toBeVisible();
  await expect(seatA2).toBeDisabled();
  await expect(seatB1).toBeDisabled();
  await expect(page.getByText("Selected 0 · Available 7 · Taken 5")).toBeVisible();

  await page.reload();

  await expect(seatButton(page, "A2")).toBeDisabled();
  await expect(seatButton(page, "B1")).toBeDisabled();
  await expect(page.getByText("Selected 0 · Available 7 · Taken 5")).toBeVisible();
});
