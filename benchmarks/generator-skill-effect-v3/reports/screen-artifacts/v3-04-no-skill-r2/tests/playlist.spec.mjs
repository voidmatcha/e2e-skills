import { expect, test } from "@playwright/test";

const titles = ["Blue in Green", "So What", "Freddie Freeloader", "All Blues"];

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.locator("#pl-tracks .title")).toHaveCount(4);
});

const order = (page) => expect(page.locator("#pl-tracks .title"));

test("lists the seeded tracks and total", async ({ page }) => {
  await order(page).toHaveText(titles);
  await expect(page.locator("#pl-tracks .length")).toHaveText(["5:37", "9:22", "9:49", "11:33"]);
  await expect(page.locator("#pl-total")).toHaveText("Total 36:21");
});

test("play shows now playing and stop hides it", async ({ page }) => {
  const now = page.locator("#pl-now");
  await expect(now).toBeHidden();
  await page.getByRole("button", { name: "Play So What" }).click();
  await expect(now).toBeVisible();
  await expect(page.locator("#pl-now-title")).toHaveText("So What");
  await page.getByRole("button", { name: "Stop" }).click();
  await expect(now).toBeHidden();
});

test("move up reorders and persists across reload", async ({ page }) => {
  await page.getByRole("button", { name: "Move So What up" }).click();
  const expected = ["So What", "Blue in Green", "Freddie Freeloader", "All Blues"];
  await order(page).toHaveText(expected);
  await page.reload();
  await order(page).toHaveText(expected);
});

test("move down reorders and persists across reload", async ({ page }) => {
  await page.getByRole("button", { name: "Move Freddie Freeloader down" }).click();
  const expected = ["Blue in Green", "So What", "All Blues", "Freddie Freeloader"];
  await order(page).toHaveText(expected);
  await page.reload();
  await order(page).toHaveText(expected);
});

test("remove deletes a track and updates the total", async ({ page }) => {
  await page.getByRole("button", { name: "Remove So What" }).click();
  await order(page).toHaveText(["Blue in Green", "Freddie Freeloader", "All Blues"]);
  // 36:21 - 9:22
  await expect(page.locator("#pl-total")).toHaveText("Total 26:59");
});

test("repeat toggle reports aria-pressed and is remembered", async ({ page }) => {
  const repeat = page.getByRole("button", { name: "Repeat" });
  await expect(repeat).toHaveAttribute("aria-pressed", "false");
  await repeat.click();
  await expect(repeat).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await expect(repeat).toHaveAttribute("aria-pressed", "true");
  await repeat.click();
  await expect(repeat).toHaveAttribute("aria-pressed", "false");
});
