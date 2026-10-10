import { expect, test } from "@playwright/test";

const seat = (page, id) => page.getByRole("button", { name: `Seat ${id}` });
const legend = (page) => page.locator("#sp-legend");
const selectedLine = (page) => page.locator("#sp-selected");
const message = (page) => page.locator("#sp-message");
const reserve = (page) => page.getByRole("button", { name: "Reserve" });

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(legend(page)).toHaveText("Selected 0 · Available 9 · Taken 3");
});

test("renders twelve seats with A1, B3 and C4 taken", async ({ page }) => {
  await expect(page.locator(".seat")).toHaveCount(12);
  for (const id of ["A1", "B3", "C4"]) await expect(seat(page, id)).toBeDisabled();
  for (const id of ["A2", "A3", "A4", "B1", "B2", "B4", "C1", "C2", "C3"]) {
    await expect(seat(page, id)).toBeEnabled();
    await expect(seat(page, id)).toHaveAttribute("aria-pressed", "false");
  }
  await expect(selectedLine(page)).toHaveText("Selected: none");
  await expect(reserve(page)).toBeDisabled();
});

test("clicking a free seat selects it and clicking again deselects it", async ({ page }) => {
  await seat(page, "A2").click();
  await expect(seat(page, "A2")).toHaveAttribute("aria-pressed", "true");
  await expect(selectedLine(page)).toHaveText("Selected: A2");
  await expect(legend(page)).toHaveText("Selected 1 · Available 8 · Taken 3");

  await seat(page, "B1").click();
  await expect(selectedLine(page)).toHaveText("Selected: A2, B1");
  await expect(legend(page)).toHaveText("Selected 2 · Available 7 · Taken 3");

  await seat(page, "A2").click();
  await expect(seat(page, "A2")).toHaveAttribute("aria-pressed", "false");
  await expect(selectedLine(page)).toHaveText("Selected: B1");
  await expect(legend(page)).toHaveText("Selected 1 · Available 8 · Taken 3");

  await seat(page, "B1").click();
  await expect(selectedLine(page)).toHaveText("Selected: none");
  await expect(legend(page)).toHaveText("Selected 0 · Available 9 · Taken 3");
  await expect(reserve(page)).toBeDisabled();
});

test("a fifth seat is refused with a message", async ({ page }) => {
  for (const id of ["A2", "A3", "A4", "B1"]) await seat(page, id).click();
  await expect(legend(page)).toHaveText("Selected 4 · Available 5 · Taken 3");

  await seat(page, "B2").click();
  await expect(message(page)).toHaveText("You can pick up to 4 seats");
  await expect(seat(page, "B2")).toHaveAttribute("aria-pressed", "false");
  await expect(selectedLine(page)).toHaveText("Selected: A2, A3, A4, B1");
  await expect(legend(page)).toHaveText("Selected 4 · Available 5 · Taken 3");

  // Deselecting frees a slot again and clears the message.
  await seat(page, "A2").click();
  await expect(message(page)).toHaveText("");
  await seat(page, "B2").click();
  await expect(selectedLine(page)).toHaveText("Selected: A3, A4, B1, B2");
});

test("reserving turns the selection into taken seats", async ({ page }) => {
  await seat(page, "A2").click();
  await seat(page, "B1").click();
  await reserve(page).click();

  await expect(page.locator("#sp-confirmation")).toHaveText("Reserved A2, B1");
  await expect(seat(page, "A2")).toBeDisabled();
  await expect(seat(page, "B1")).toBeDisabled();
  await expect(seat(page, "A2")).toHaveAttribute("aria-pressed", "false");
  await expect(selectedLine(page)).toHaveText("Selected: none");
  await expect(legend(page)).toHaveText("Selected 0 · Available 7 · Taken 5");
  await expect(reserve(page)).toBeDisabled();
});

test("reservations survive a reload", async ({ page }) => {
  await seat(page, "C1").click();
  await seat(page, "C2").click();
  await reserve(page).click();
  await expect(legend(page)).toHaveText("Selected 0 · Available 7 · Taken 5");

  await page.reload();
  await expect(legend(page)).toHaveText("Selected 0 · Available 7 · Taken 5");
  await expect(seat(page, "C1")).toBeDisabled();
  await expect(seat(page, "C2")).toBeDisabled();
  await expect(selectedLine(page)).toHaveText("Selected: none");
});
