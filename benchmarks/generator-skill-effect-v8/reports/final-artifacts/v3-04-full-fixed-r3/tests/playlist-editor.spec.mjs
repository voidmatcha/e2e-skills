import { expect, test } from "@playwright/test";

const tracks = (page) => page.getByRole("list", { name: "Tracks", exact: true }).getByRole("listitem");

const expectTrackOrder = async (page, titles) => {
  await expect(tracks(page)).toContainText(titles);
};

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("shows seeded tracks and controls playback", async ({ page }) => {
  await expect(tracks(page)).toHaveCount(4);
  await expectTrackOrder(page, ["Blue in Green", "So What", "Freddie Freeloader", "All Blues"]);
  await expect(tracks(page).filter({ hasText: "Blue in Green" })).toContainText("5:37");
  await expect(tracks(page).filter({ hasText: "So What" })).toContainText("9:22");
  await expect(tracks(page).filter({ hasText: "Freddie Freeloader" })).toContainText("9:49");
  await expect(tracks(page).filter({ hasText: "All Blues" })).toContainText("11:33");

  await page.getByRole("button", { name: "Play So What", exact: true }).click();

  await expect(page.getByText("Now playing: So What")).toBeVisible();

  await page.getByRole("button", { name: "Stop", exact: true }).click();
  await expect(page.getByText("Now playing: So What")).toBeHidden();
});

test("reorders tracks and keeps the order after reload", async ({ page }) => {
  const firstOrder = page.waitForRequest((request) => request.method() === "PUT" && request.url().endsWith("/api/order"));
  await page.getByRole("button", { name: "Move Blue in Green down", exact: true }).click();
  await firstOrder;
  await expectTrackOrder(page, ["So What", "Blue in Green", "Freddie Freeloader", "All Blues"]);

  const secondOrder = page.waitForRequest((request) => request.method() === "PUT" && request.url().endsWith("/api/order"));
  await page.getByRole("button", { name: "Move All Blues up", exact: true }).click();
  await secondOrder;

  await page.reload();
  await expectTrackOrder(page, ["So What", "Blue in Green", "All Blues", "Freddie Freeloader"]);
});

test("updates the total when a track is removed", async ({ page }) => {
  await expect(page.getByText("Total 36:21")).toBeVisible();

  const deleteTrack = page.waitForRequest((request) => request.method() === "DELETE" && request.url().endsWith("/api/tracks/3"));
  await page.getByRole("button", { name: "Remove Freddie Freeloader", exact: true }).click();
  await deleteTrack;

  await expect(tracks(page)).toHaveCount(3);
  await expect(tracks(page).filter({ hasText: "Freddie Freeloader" })).toHaveCount(0);
  await expect(page.getByText("Total 26:32")).toBeVisible();
});

test("persists the repeat setting across reloads", async ({ page }) => {
  const repeat = page.getByRole("button", { name: "Repeat", exact: true });
  await expect(repeat).toHaveAttribute("aria-pressed", "false");

  const saveRepeat = page.waitForRequest((request) => request.method() === "PATCH" && request.url().endsWith("/api/repeat"));
  await repeat.click();
  await saveRepeat;

  await expect(repeat).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await expect(page.getByRole("button", { name: "Repeat", exact: true })).toHaveAttribute("aria-pressed", "true");
});
