import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const seat = (page, id) => page.getByRole("button", { name: `Seat ${id}` });

test("selects and deselects available seats", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("#sp-legend")).toHaveText("Selected 0 · Available 9 · Taken 3");
  await expect(page.locator("#sp-selected")).toHaveText("Selected: none");
  await expect(seat(page, "A1")).toBeDisabled();

  await seat(page, "A2").click();
  await expect(seat(page, "A2")).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#sp-selected")).toHaveText("Selected: A2");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 1 · Available 8 · Taken 3");

  await seat(page, "B1").click();
  await expect(seat(page, "B1")).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#sp-selected")).toHaveText("Selected: A2, B1");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 2 · Available 7 · Taken 3");

  await seat(page, "A2").click();
  await expect(seat(page, "A2")).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator("#sp-selected")).toHaveText("Selected: B1");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 1 · Available 8 · Taken 3");
});

test("limits selection to four seats", async ({ page }) => {
  await page.goto("/");

  for (const id of ["A2", "A3", "A4", "B1"]) {
    await seat(page, id).click();
  }

  await expect(page.locator("#sp-selected")).toHaveText("Selected: A2, A3, A4, B1");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 4 · Available 5 · Taken 3");

  await seat(page, "B2").click();
  await expect(page.locator("#sp-message")).toHaveText("You can pick up to 4 seats");
  await expect(seat(page, "B2")).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator("#sp-selected")).toHaveText("Selected: A2, A3, A4, B1");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 4 · Available 5 · Taken 3");
});

test("reserves selected seats and keeps them taken after reload", async ({ page }) => {
  await page.goto("/");

  await seat(page, "A2").click();
  await seat(page, "B1").click();
  await page.getByRole("button", { name: "Reserve" }).click();

  await expect(page.locator("#sp-confirmation")).toHaveText("Reserved A2, B1");
  await expect(page.locator("#sp-selected")).toHaveText("Selected: none");
  await expect(page.locator("#sp-legend")).toHaveText("Selected 0 · Available 7 · Taken 5");
  await expect(seat(page, "A2")).toBeDisabled();
  await expect(seat(page, "B1")).toBeDisabled();

  await page.reload();
  await expect(page.locator("#sp-legend")).toHaveText("Selected 0 · Available 7 · Taken 5");
  await expect(page.locator("#sp-selected")).toHaveText("Selected: none");
  await expect(seat(page, "A2")).toBeDisabled();
  await expect(seat(page, "B1")).toBeDisabled();
});
