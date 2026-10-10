import { expect, test } from "@playwright/test";

const slots = (page) => page.getByRole("list", { name: "Slots" }).getByRole("listitem");
const mine = (page) => page.getByRole("list", { name: "My bookings" }).getByRole("listitem");
const heading = (page) => page.getByRole("heading", { name: /My bookings/ });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(slots(page)).toHaveCount(3);
});

test("booking a slot lists it, marks it yours and survives a reload", async ({ page }) => {
  await page.getByRole("tab", { name: "Tue 13" }).click();
  await page.getByRole("button", { name: "Book 10:00 on Tue 13" }).click();
  await expect(mine(page)).toHaveText([/Tue 13 10:00/]);
  await expect(slots(page).filter({ hasText: "10:00" })).toContainText("Yours");
  await expect(heading(page)).toHaveText("My bookings (1)");
  await page.reload();
  await expect(mine(page)).toHaveText([/Tue 13 10:00/]);
  await page.getByRole("tab", { name: "Tue 13" }).click();
  await expect(slots(page).filter({ hasText: "10:00" })).toContainText("Yours");
  await expect(page.getByRole("button", { name: "Book 10:00 on Tue 13" })).toHaveCount(0);
});

test("cancelling frees the slot so it can be booked again", async ({ page }) => {
  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();
  await expect(mine(page)).toHaveCount(1);
  await page.getByRole("button", { name: "Cancel Mon 12 09:00" }).click();
  await expect(mine(page)).toHaveCount(0);
  await expect(heading(page)).toHaveText("My bookings (0)");
  await expect(page.getByRole("button", { name: "Book 09:00 on Mon 12" })).toBeVisible();
  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();
  await expect(mine(page)).toHaveText([/Mon 12 09:00/]);
});

test("a slot taken by someone else shows the message and refreshes", async ({ page }) => {
  await page.request.post("/api/dev/take", { data: { date: "Mon 12", time: "11:00" } });
  await page.getByRole("button", { name: "Book 11:00 on Mon 12" }).click();
  await expect(page.getByRole("alert")).toHaveText("That slot was just taken");
  await expect(slots(page).filter({ hasText: "11:00" })).toContainText("Taken");
  await expect(page.getByRole("button", { name: "Book 11:00 on Mon 12" })).toHaveCount(0);
  await expect(mine(page)).toHaveCount(0);
});

test("the heading counts bookings", async ({ page }) => {
  await page.getByRole("button", { name: "Book 09:00 on Mon 12" }).click();
  await page.getByRole("button", { name: "Book 10:00 on Mon 12" }).click();
  await expect(mine(page)).toHaveCount(2);
  await expect(heading(page)).toHaveText("My bookings (2)");
});
