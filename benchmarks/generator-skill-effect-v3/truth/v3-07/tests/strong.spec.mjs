import { expect, test } from "@playwright/test";

const seat = (page, id) => page.getByRole("button", { name: `Seat ${id}` });
const legend = (page) => page.getByText(/^Selected \d+ · Available \d+ · Taken \d+$/);
const selectedLine = (page) => page.getByText(/^Selected: /);

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(legend(page)).toHaveText("Selected 0 · Available 9 · Taken 3");
  await expect(seat(page, "A1")).toBeDisabled();
});

test("selecting and deselecting updates aria-pressed, the selected line and the legend", async ({ page }) => {
  await seat(page, "A2").click();
  await expect(seat(page, "A2")).toHaveAttribute("aria-pressed", "true");
  await expect(selectedLine(page)).toHaveText("Selected: A2");
  await expect(legend(page)).toHaveText("Selected 1 · Available 8 · Taken 3");
  await seat(page, "B1").click();
  await expect(selectedLine(page)).toHaveText("Selected: A2, B1");
  await seat(page, "A2").click();
  await expect(seat(page, "A2")).toHaveAttribute("aria-pressed", "false");
  await expect(selectedLine(page)).toHaveText("Selected: B1");
  await expect(legend(page)).toHaveText("Selected 1 · Available 8 · Taken 3");
});

test("at most four seats can be selected", async ({ page }) => {
  for (const id of ["A2", "A3", "A4", "B1"]) await seat(page, id).click();
  await expect(legend(page)).toHaveText("Selected 4 · Available 5 · Taken 3");
  await seat(page, "B2").click();
  await expect(page.getByText("You can pick up to 4 seats")).toBeVisible();
  await expect(seat(page, "B2")).toHaveAttribute("aria-pressed", "false");
  await expect(selectedLine(page)).toHaveText("Selected: A2, A3, A4, B1");
  await expect(legend(page)).toHaveText("Selected 4 · Available 5 · Taken 3");
});

test("reserve makes the seats taken and persists", async ({ page }) => {
  await seat(page, "A2").click();
  await seat(page, "B1").click();
  await page.getByRole("button", { name: "Reserve" }).click();
  await expect(page.getByText("Reserved A2, B1")).toBeVisible();
  await expect(seat(page, "A2")).toBeDisabled();
  await expect(seat(page, "B1")).toBeDisabled();
  await expect(selectedLine(page)).toHaveText("Selected: none");
  await expect(legend(page)).toHaveText("Selected 0 · Available 7 · Taken 5");
  await page.reload();
  await expect(seat(page, "A2")).toBeDisabled();
  await expect(legend(page)).toHaveText("Selected 0 · Available 7 · Taken 5");
});
