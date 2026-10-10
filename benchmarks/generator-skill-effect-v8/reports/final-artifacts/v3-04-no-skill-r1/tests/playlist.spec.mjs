import { expect, test } from "@playwright/test";

const seedTitles = ["Blue in Green", "So What", "Freddie Freeloader", "All Blues"];

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const expectTrackOrder = async (page, titles) => {
  const tracks = page.getByRole("list", { name: "Tracks" }).getByRole("listitem");
  await expect(tracks).toHaveCount(titles.length);

  for (const [index, title] of titles.entries()) {
    await expect(tracks.nth(index)).toContainText(title);
  }
};

test("shows the seeded playlist and total length", async ({ page }) => {
  await page.goto("/");

  await expectTrackOrder(page, seedTitles);
  await expect(page.getByText("5:37")).toBeVisible();
  await expect(page.getByText("9:22")).toBeVisible();
  await expect(page.getByText("9:49")).toBeVisible();
  await expect(page.getByText("11:33")).toBeVisible();
  await expect(page.getByText("Total 36:21")).toBeVisible();
});

test("plays a track and stops playback", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Play So What" }).click();
  const nowPlaying = page.locator("#pl-now");
  await expect(nowPlaying).toBeVisible();
  await expect(nowPlaying).toContainText("So What");

  await page.getByRole("button", { name: "Stop" }).click();
  await expect(nowPlaying).toBeHidden();
});

test("reorders tracks and keeps the new order after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Move So What up" }).click();
  await expectTrackOrder(page, ["So What", "Blue in Green", "Freddie Freeloader", "All Blues"]);

  await page.getByRole("button", { name: "Move Blue in Green down" }).click();
  await expectTrackOrder(page, ["So What", "Freddie Freeloader", "Blue in Green", "All Blues"]);

  await page.reload();
  await expectTrackOrder(page, ["So What", "Freddie Freeloader", "Blue in Green", "All Blues"]);
});

test("removes a track and updates the total length", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Remove Freddie Freeloader" }).click();

  await expectTrackOrder(page, ["Blue in Green", "So What", "All Blues"]);
  await expect(page.getByText("Freddie Freeloader")).toHaveCount(0);
  await expect(page.getByText("Total 26:32")).toBeVisible();
});

test("remembers the repeat setting after reload", async ({ page }) => {
  await page.goto("/");

  const repeat = page.getByRole("button", { name: "Repeat" });
  await expect(repeat).toHaveAttribute("aria-pressed", "false");

  await repeat.click();
  await expect(repeat).toHaveAttribute("aria-pressed", "true");

  await page.reload();
  await expect(page.getByRole("button", { name: "Repeat" })).toHaveAttribute("aria-pressed", "true");
});
