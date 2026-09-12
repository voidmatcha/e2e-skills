import { expect, test } from "@playwright/test";

test("eventually displays four available reading-room seats", async ({ page }) => {
  await page.goto("/reading-room/today");
  const availableSeats = page.getByTestId("available-seat-count");

  await expect.poll(async () => await availableSeats.textContent()).toBe("4");
});
