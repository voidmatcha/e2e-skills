import { expect, test } from "@playwright/test";

const seat = (page, label) => page.getByRole("button", { name: `Seat ${label}`, exact: true });
const legend = (page, selected, available, taken) => {
  return page.getByText(`Selected ${selected} · Available ${available} · Taken ${taken}`);
};
const selectedLine = (page, text) => page.getByText(`Selected: ${text}`);

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("shows the seeded seat map and legend", async ({ page }) => {
  for (const label of ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "C1", "C2", "C3", "C4"]) {
    await expect(seat(page, label)).toBeVisible();
  }

  await expect(seat(page, "A1")).toBeDisabled();
  await expect(seat(page, "B3")).toBeDisabled();
  await expect(seat(page, "C4")).toBeDisabled();
  await expect(legend(page, 0, 9, 3)).toBeVisible();
  await expect(selectedLine(page, "none")).toBeVisible();
});

test("selects and deselects free seats", async ({ page }) => {
  await seat(page, "A2").click();
  await seat(page, "B1").click();

  await expect(seat(page, "A2")).toHaveAttribute("aria-pressed", "true");
  await expect(seat(page, "B1")).toHaveAttribute("aria-pressed", "true");
  await expect(selectedLine(page, "A2, B1")).toBeVisible();
  await expect(legend(page, 2, 7, 3)).toBeVisible();

  await seat(page, "A2").click();

  await expect(seat(page, "A2")).not.toHaveAttribute("aria-pressed", "true");
  await expect(selectedLine(page, "B1")).toBeVisible();
  await expect(legend(page, 1, 8, 3)).toBeVisible();
});

test("keeps selection capped at four seats", async ({ page }) => {
  for (const label of ["A2", "A3", "A4", "B1"]) {
    await seat(page, label).click();
  }

  await seat(page, "B2").click();

  await expect(page.getByText("You can pick up to 4 seats")).toBeVisible();
  await expect(seat(page, "B2")).not.toHaveAttribute("aria-pressed", "true");
  await expect(selectedLine(page, "A2, A3, A4, B1")).toBeVisible();
  await expect(legend(page, 4, 5, 3)).toBeVisible();
});

test("reserves selected seats and keeps them taken after reload", async ({ page }) => {
  const reservationRequests = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/reservations") {
      reservationRequests.push(request);
    }
  });

  await seat(page, "A2").click();
  await seat(page, "B1").click();

  const reservationRequest = page.waitForRequest(
    (request) => request.method() === "POST" && new URL(request.url()).pathname === "/api/reservations",
  );
  await page.getByRole("button", { name: "Reserve", exact: true }).click();
  const request = await reservationRequest;

  expect(JSON.parse(request.postData())).toEqual({ seats: ["A2", "B1"] });
  await expect(page.getByText("Reserved A2, B1")).toBeVisible();
  expect(reservationRequests).toHaveLength(1);
  await expect(legend(page, 0, 7, 5)).toBeVisible();
  await expect(selectedLine(page, "none")).toBeVisible();
  await expect(seat(page, "A2")).toBeDisabled();
  await expect(seat(page, "B1")).toBeDisabled();

  await page.reload();

  await expect(seat(page, "A2")).toBeDisabled();
  await expect(seat(page, "B1")).toBeDisabled();
  await expect(legend(page, 0, 7, 5)).toBeVisible();
});
