import { expect, test } from "@playwright/test";

const seat = (page, id) => page.getByRole("button", { name: `Seat ${id}`, exact: true });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 0 · Available 9 · Taken 3");
});

test("shows the seeded taken seats as disabled", async ({ page }) => {
  for (const id of ["A1", "B3", "C4"]) await expect(seat(page, id)).toBeDisabled();
  await expect(seat(page, "A2")).toBeEnabled();
  await expect(page.locator("#sp-selected")).toHaveText("Selected: none");
  await expect(page.getByRole("button", { name: "Reserve" })).toBeDisabled();
});

test("selects and deselects a seat", async ({ page }) => {
  await seat(page, "A2").click();
  await expect(seat(page, "A2")).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#sp-selected")).toHaveText("Selected: A2");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 1 · Available 8 · Taken 3");

  await seat(page, "A2").click();
  await expect(seat(page, "A2")).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator("#sp-selected")).toHaveText("Selected: none");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 0 · Available 9 · Taken 3");
});

test("lists selected seats and updates the legend", async ({ page }) => {
  await seat(page, "A2").click();
  await seat(page, "B1").click();
  await expect(page.locator("#sp-selected")).toHaveText("Selected: A2, B1");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 2 · Available 7 · Taken 3");
});

test("limits the selection to 4 seats", async ({ page }) => {
  for (const id of ["A2", "A3", "A4", "B1"]) await seat(page, id).click();
  await expect(page.locator("#sp-legend")).toHaveText("Selected 4 · Available 5 · Taken 3");

  await seat(page, "B2").click();
  await expect(page.locator("#sp-message")).toHaveText("You can pick up to 4 seats");
  await expect(seat(page, "B2")).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator("#sp-selected")).toHaveText("Selected: A2, A3, A4, B1");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 4 · Available 5 · Taken 3");
});

test("reserve takes the selected seats and clears the selection", async ({ page }) => {
  await seat(page, "A2").click();
  await seat(page, "B1").click();
  await page.getByRole("button", { name: "Reserve" }).click();

  await expect(page.locator("#sp-confirmation")).toHaveText("Reserved A2, B1");
  await expect(page.locator("#sp-selected")).toHaveText("Selected: none");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 0 · Available 7 · Taken 5");
  await expect(seat(page, "A2")).toBeDisabled();
  await expect(seat(page, "B1")).toBeDisabled();
  await expect(page.getByRole("button", { name: "Reserve" })).toBeDisabled();
});

test("reservations survive a reload", async ({ page }) => {
  await seat(page, "C1").click();
  await page.getByRole("button", { name: "Reserve" }).click();
  await expect(page.locator("#sp-confirmation")).toHaveText("Reserved C1");

  await page.reload();
  await expect(page.locator("#sp-legend")).toHaveText("Selected 0 · Available 8 · Taken 4");
  await expect(seat(page, "C1")).toBeDisabled();
});
