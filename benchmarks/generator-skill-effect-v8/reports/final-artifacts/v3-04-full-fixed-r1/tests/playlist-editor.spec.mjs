import { expect, test } from "@playwright/test";

const seededTracks = [
  /Blue in Green5:37/,
  /So What9:22/,
  /Freddie Freeloader9:49/,
  /All Blues11:33/,
];

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("plays and stops a track", async ({ page }) => {
  await page.goto("/");

  const nowPlaying = page.getByText("Now playing: So What");

  await page.getByRole("button", { name: /^Play So What$/ }).click();
  await expect(nowPlaying).toBeVisible();

  await page.getByRole("button", { name: /^Stop$/ }).click();
  await expect(nowPlaying).toBeHidden();
});

test("moves tracks up and down and keeps the order after reload", async ({ page }) => {
  await page.goto("/");

  const tracks = page.getByRole("list", { name: /^Tracks$/ }).getByRole("listitem");
  await expect(tracks).toContainText(seededTracks);

  const moveDown = page.waitForRequest((request) => (
    request.method() === "PUT" &&
    request.url().endsWith("/api/order") &&
    request.postDataJSON().order.join(",") === "1,3,2,4"
  ));
  await page.getByRole("button", { name: /^Move So What down$/ }).click();
  await moveDown;
  await expect(tracks).toContainText([
    /Blue in Green5:37/,
    /Freddie Freeloader9:49/,
    /So What9:22/,
    /All Blues11:33/,
  ]);

  const moveUp = page.waitForRequest((request) => (
    request.method() === "PUT" &&
    request.url().endsWith("/api/order") &&
    request.postDataJSON().order.join(",") === "1,2,3,4"
  ));
  await page.getByRole("button", { name: /^Move So What up$/ }).click();
  await moveUp;
  await expect(tracks).toContainText(seededTracks);

  await page.reload();
  await expect(tracks).toContainText(seededTracks);
});

test("removes a track and updates the total", async ({ page }) => {
  await page.goto("/");

  const tracks = page.getByRole("list", { name: /^Tracks$/ }).getByRole("listitem");
  await expect(page.getByText("Total 36:21")).toBeVisible();

  const remove = page.waitForRequest((request) => (
    request.method() === "DELETE" &&
    request.url().endsWith("/api/tracks/3")
  ));
  await page.getByRole("button", { name: /^Remove Freddie Freeloader$/ }).click();
  await remove;

  await expect(page.getByText("Total 26:32")).toBeVisible();
  await expect(tracks).toContainText([
    /Blue in Green5:37/,
    /So What9:22/,
    /All Blues11:33/,
  ]);
  await expect(page.getByRole("button", { name: /^Remove Freddie Freeloader$/ })).not.toBeAttached();
});

test("persists repeat through aria-pressed across reload", async ({ page }) => {
  await page.goto("/");

  const repeat = page.getByRole("button", { name: /^Repeat$/ });
  await expect(repeat).toHaveAttribute("aria-pressed", "false");

  const toggle = page.waitForRequest((request) => (
    request.method() === "PATCH" &&
    request.url().endsWith("/api/repeat") &&
    request.postDataJSON().repeat === true
  ));
  await repeat.click();
  await toggle;
  await expect(repeat).toHaveAttribute("aria-pressed", "true");

  await page.reload();
  await expect(repeat).toHaveAttribute("aria-pressed", "true");
});
