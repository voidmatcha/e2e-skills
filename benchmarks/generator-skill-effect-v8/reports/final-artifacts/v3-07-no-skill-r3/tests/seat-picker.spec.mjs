import { expect, test } from "@playwright/test";

const seat = (page, id) => page.getByRole("button", { name: `Seat ${id}` });
const expectLegend = async (page, text) => {
  await expect(page.locator("#sp-legend")).toHaveText(text);
};
const expectSelected = async (page, text) => {
  await expect(page.locator("#sp-selected")).toHaveText(`Selected: ${text}`);
};

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("shows all seats with seeded taken seats", async ({ page }) => {
  await expect(page.getByRole("button", { name: /^Seat [ABC][1-4]$/ })).toHaveCount(12);

  await expect(seat(page, "A1")).toBeDisabled();
  await expect(seat(page, "B3")).toBeDisabled();
  await expect(seat(page, "C4")).toBeDisabled();

  await expect(seat(page, "A2")).toBeEnabled();
  await expect(seat(page, "B1")).toBeEnabled();
  await expectLegend(page, "Selected 0 · Available 9 · Taken 3");
  await expectSelected(page, "none");
});

test("selects, deselects, and enforces the four-seat limit", async ({ page }) => {
  await seat(page, "A2").click();
  await seat(page, "B1").click();

  await expect(seat(page, "A2")).toHaveAttribute("aria-pressed", "true");
  await expect(seat(page, "B1")).toHaveAttribute("aria-pressed", "true");
  await expectSelected(page, "A2, B1");
  await expectLegend(page, "Selected 2 · Available 7 · Taken 3");

  await seat(page, "A2").click();

  await expect(seat(page, "A2")).toHaveAttribute("aria-pressed", "false");
  await expectSelected(page, "B1");
  await expectLegend(page, "Selected 1 · Available 8 · Taken 3");

  await seat(page, "A2").click();
  await seat(page, "B2").click();
  await seat(page, "C1").click();

  await expectSelected(page, "B1, A2, B2, C1");
  await expectLegend(page, "Selected 4 · Available 5 · Taken 3");

  await seat(page, "C2").click();

  await expect(page.locator("#sp-message")).toHaveText("You can pick up to 4 seats");
  await expect(seat(page, "C2")).toHaveAttribute("aria-pressed", "false");
  await expectSelected(page, "B1, A2, B2, C1");
  await expectLegend(page, "Selected 4 · Available 5 · Taken 3");
});

test("reserves selected seats and persists them after reload", async ({ page }) => {
  await seat(page, "A2").click();
  await seat(page, "B1").click();
  await page.getByRole("button", { name: "Reserve" }).click();

  await expect(page.locator("#sp-confirmation")).toHaveText("Reserved A2, B1");
  await expectSelected(page, "none");
  await expectLegend(page, "Selected 0 · Available 7 · Taken 5");
  await expect(seat(page, "A2")).toBeDisabled();
  await expect(seat(page, "B1")).toBeDisabled();

  await page.reload();

  await expect(seat(page, "A2")).toBeDisabled();
  await expect(seat(page, "B1")).toBeDisabled();
  await expectSelected(page, "none");
  await expectLegend(page, "Selected 0 · Available 7 · Taken 5");
});
