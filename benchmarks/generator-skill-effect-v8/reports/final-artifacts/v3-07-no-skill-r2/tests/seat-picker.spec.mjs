import { expect, test } from "@playwright/test";

const seatIds = ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "C1", "C2", "C3", "C4"];
const takenSeats = ["A1", "B3", "C4"];

const seat = (page, id) => page.getByRole("button", { name: `Seat ${id}` });
const legend = (page) => page.locator("#sp-legend");
const selectedLine = (page) => page.locator("#sp-selected");

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shows the seeded seats and toggles free seat selections", async ({ page }) => {
  await page.goto("/");

  for (const id of seatIds) {
    await expect(seat(page, id)).toBeVisible();
  }

  for (const id of takenSeats) {
    await expect(seat(page, id)).toBeDisabled();
  }

  await expect(legend(page)).toHaveText("Selected 0 · Available 9 · Taken 3");
  await expect(selectedLine(page)).toHaveText("Selected: none");

  await seat(page, "A2").click();
  await expect(seat(page, "A2")).toHaveAttribute("aria-pressed", "true");
  await expect(legend(page)).toHaveText("Selected 1 · Available 8 · Taken 3");
  await expect(selectedLine(page)).toHaveText("Selected: A2");

  await seat(page, "B1").click();
  await expect(seat(page, "B1")).toHaveAttribute("aria-pressed", "true");
  await expect(legend(page)).toHaveText("Selected 2 · Available 7 · Taken 3");
  await expect(selectedLine(page)).toHaveText("Selected: A2, B1");

  await seat(page, "A2").click();
  await expect(seat(page, "A2")).toHaveAttribute("aria-pressed", "false");
  await expect(legend(page)).toHaveText("Selected 1 · Available 8 · Taken 3");
  await expect(selectedLine(page)).toHaveText("Selected: B1");
});

test("limits selection to four seats", async ({ page }) => {
  await page.goto("/");

  for (const id of ["A2", "A3", "A4", "B1"]) {
    await seat(page, id).click();
  }

  await expect(legend(page)).toHaveText("Selected 4 · Available 5 · Taken 3");
  await expect(selectedLine(page)).toHaveText("Selected: A2, A3, A4, B1");

  await seat(page, "B2").click();
  await expect(page.locator("#sp-message")).toHaveText("You can pick up to 4 seats");
  await expect(seat(page, "B2")).toHaveAttribute("aria-pressed", "false");
  await expect(legend(page)).toHaveText("Selected 4 · Available 5 · Taken 3");
  await expect(selectedLine(page)).toHaveText("Selected: A2, A3, A4, B1");
});

test("reserves selected seats and keeps them taken after reload", async ({ page }) => {
  await page.goto("/");

  await seat(page, "A2").click();
  await seat(page, "B1").click();
  await page.getByRole("button", { name: "Reserve" }).click();

  await expect(page.locator("#sp-confirmation")).toHaveText("Reserved A2, B1");
  await expect(selectedLine(page)).toHaveText("Selected: none");
  await expect(legend(page)).toHaveText("Selected 0 · Available 7 · Taken 5");
  await expect(seat(page, "A2")).toBeDisabled();
  await expect(seat(page, "B1")).toBeDisabled();

  await page.reload();

  await expect(seat(page, "A2")).toBeDisabled();
  await expect(seat(page, "B1")).toBeDisabled();
  await expect(selectedLine(page)).toHaveText("Selected: none");
  await expect(legend(page)).toHaveText("Selected 0 · Available 7 · Taken 5");
});
