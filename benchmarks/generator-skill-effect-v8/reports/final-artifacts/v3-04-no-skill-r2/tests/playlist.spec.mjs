import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

const trackTitles = (page) =>
  page.getByRole("list", { name: "Tracks" }).getByRole("listitem").locator(".title").allTextContents();

test("plays and stops a track", async ({ page }) => {
  await page.getByRole("button", { name: "Play So What" }).click();

  const nowPlaying = page.locator("#pl-now");
  await expect(nowPlaying).toBeVisible();
  await expect(nowPlaying).toContainText("So What");

  await page.getByRole("button", { name: "Stop" }).click();
  await expect(nowPlaying).toBeHidden();
});

test("moves tracks up and down and keeps the new order after reload", async ({ page }) => {
  await expect.poll(() => trackTitles(page)).toEqual([
    "Blue in Green",
    "So What",
    "Freddie Freeloader",
    "All Blues",
  ]);

  await page.getByRole("button", { name: "Move So What up" }).click();
  await page.getByRole("button", { name: "Move Freddie Freeloader down" }).click();

  await expect.poll(() => trackTitles(page)).toEqual([
    "So What",
    "Blue in Green",
    "All Blues",
    "Freddie Freeloader",
  ]);

  await page.reload();

  await expect.poll(() => trackTitles(page)).toEqual([
    "So What",
    "Blue in Green",
    "All Blues",
    "Freddie Freeloader",
  ]);
});

test("updates the total when a track is removed", async ({ page }) => {
  await expect(page.locator("#pl-total")).toHaveText("Total 36:21");

  await page.getByRole("button", { name: "Remove Blue in Green" }).click();

  await expect(page.locator("#pl-total")).toHaveText("Total 30:44");
  await expect.poll(() => trackTitles(page)).toEqual([
    "So What",
    "Freddie Freeloader",
    "All Blues",
  ]);
});

test("remembers the repeat setting across reloads", async ({ page }) => {
  const repeat = page.getByRole("button", { name: "Repeat" });
  await expect(repeat).toHaveAttribute("aria-pressed", "false");

  await repeat.click();
  await expect(repeat).toHaveAttribute("aria-pressed", "true");

  await page.reload();
  await expect(page.getByRole("button", { name: "Repeat" })).toHaveAttribute("aria-pressed", "true");
});
