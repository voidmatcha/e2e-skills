import { expect, test } from "@playwright/test";

const seededTracks = [
  "Blue in Green",
  "So What",
  "Freddie Freeloader",
  "All Blues",
];

const tracks = (page) => page.getByRole("list", { name: "Tracks" }).getByRole("listitem");
const trackTitles = async (page) => tracks(page).locator(".title").allTextContents();

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("plays and stops a track", async ({ page }) => {
  await page.goto("/");

  await expect(tracks(page)).toHaveCount(4);
  await page.getByRole("button", { name: "Play So What" }).click();

  const nowPlaying = page.locator("#pl-now");
  await expect(nowPlaying).toBeVisible();
  await expect(nowPlaying).toContainText("So What");

  await page.getByRole("button", { name: "Stop" }).click();
  await expect(nowPlaying).toBeHidden();
});

test("moves tracks up and down and keeps the new order after reload", async ({ page }) => {
  await page.goto("/");
  await expect.poll(() => trackTitles(page)).toEqual(seededTracks);

  await page.getByRole("button", { name: "Move So What up" }).click();
  await expect.poll(() => trackTitles(page)).toEqual([
    "So What",
    "Blue in Green",
    "Freddie Freeloader",
    "All Blues",
  ]);

  await page.getByRole("button", { name: "Move Blue in Green down" }).click();
  const reorderedTracks = [
    "So What",
    "Freddie Freeloader",
    "Blue in Green",
    "All Blues",
  ];
  await expect.poll(() => trackTitles(page)).toEqual(reorderedTracks);

  await page.reload();
  await expect.poll(() => trackTitles(page)).toEqual(reorderedTracks);
});

test("shows total length and updates it after removing a track", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("#pl-total")).toHaveText("Total 36:21");
  await page.getByRole("button", { name: "Remove Freddie Freeloader" }).click();

  await expect.poll(() => trackTitles(page)).toEqual([
    "Blue in Green",
    "So What",
    "All Blues",
  ]);
  await expect(page.locator("#pl-total")).toHaveText("Total 26:32");
});

test("toggles repeat and remembers the setting after reload", async ({ page }) => {
  await page.goto("/");

  const repeat = page.getByRole("button", { name: "Repeat" });
  await expect(repeat).toHaveAttribute("aria-pressed", "false");

  await repeat.click();
  await expect(repeat).toHaveAttribute("aria-pressed", "true");

  await page.reload();
  await expect(page.getByRole("button", { name: "Repeat" })).toHaveAttribute("aria-pressed", "true");
});
