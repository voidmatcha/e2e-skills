import { expect, test } from "@playwright/test";

const seat = (page, id) => page.getByRole("button", { name: `Seat ${id}` });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 0 · Available 9 · Taken 3");
});

test("renders twelve seats with A1, B3 and C4 taken", async ({ page }) => {
  await expect(page.locator("#sp-grid button")).toHaveCount(12);
  for (const id of ["A1", "B3", "C4"]) await expect(seat(page, id)).toBeDisabled();
  for (const id of ["A2", "B1", "C1"]) await expect(seat(page, id)).toBeEnabled();
  await expect(page.locator("#sp-selected")).toHaveText("Selected: none");
  await expect(page.getByRole("button", { name: "Reserve" })).toBeDisabled();
});

test("selecting and deselecting a seat updates state, line and legend", async ({ page }) => {
  await seat(page, "A2").click();
  await expect(seat(page, "A2")).toHaveAttribute("aria-pressed", "true");
  await seat(page, "B1").click();
  await expect(page.locator("#sp-selected")).toHaveText("Selected: A2, B1");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 2 · Available 7 · Taken 3");

  await seat(page, "A2").click();
  await expect(seat(page, "A2")).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator("#sp-selected")).toHaveText("Selected: B1");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 1 · Available 8 · Taken 3");
});

test("a fifth seat is refused with a message", async ({ page }) => {
  for (const id of ["A2", "A3", "A4", "B1"]) await seat(page, id).click();
  await expect(page.locator("#sp-legend")).toHaveText("Selected 4 · Available 5 · Taken 3");

  await seat(page, "B2").click();
  await expect(page.locator("#sp-message")).toHaveText("You can pick up to 4 seats");
  await expect(seat(page, "B2")).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator("#sp-selected")).toHaveText("Selected: A2, A3, A4, B1");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 4 · Available 5 · Taken 3");
});

test("reserving makes seats taken, clears selection and persists after reload", async ({ page }) => {
  await seat(page, "A2").click();
  await seat(page, "B1").click();
  await page.getByRole("button", { name: "Reserve" }).click();

  await expect(page.locator("#sp-confirmation")).toHaveText("Reserved A2, B1");
  await expect(page.locator("#sp-selected")).toHaveText("Selected: none");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 0 · Available 7 · Taken 5");
  await expect(seat(page, "A2")).toBeDisabled();
  await expect(seat(page, "B1")).toBeDisabled();
  await expect(page.getByRole("button", { name: "Reserve" })).toBeDisabled();

  await page.reload();
  await expect(page.locator("#sp-legend")).toHaveText("Selected 0 · Available 7 · Taken 5");
  await expect(seat(page, "A2")).toBeDisabled();
  await expect(seat(page, "B1")).toBeDisabled();
});
