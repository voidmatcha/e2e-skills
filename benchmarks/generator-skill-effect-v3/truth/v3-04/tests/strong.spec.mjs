import { expect, test } from "@playwright/test";

const tracks = (page) => page.getByRole("list", { name: "Tracks" }).getByRole("listitem");
const total = (page) => page.getByText(/^Total \d+:\d{2}$/);
const nowPlaying = (page) => page.getByText("Now playing:");

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(tracks(page)).toHaveCount(4);
  await expect(total(page)).toHaveText("Total 36:21");
});

test("play shows the panel with the title and stop hides it", async ({ page }) => {
  await expect(nowPlaying(page)).toBeHidden();
  await page.getByRole("button", { name: "Play So What" }).click();
  await expect(nowPlaying(page)).toBeVisible();
  await expect(page.getByText("So What", { exact: true }).nth(1)).toBeVisible();
  await page.getByRole("button", { name: "Stop" }).click();
  await expect(nowPlaying(page)).toBeHidden();
});

test("reordering persists", async ({ page }) => {
  await page.getByRole("button", { name: "Move All Blues up" }).click();
  await expect(tracks(page)).toHaveText([/Blue in Green/, /So What/, /All Blues/, /Freddie Freeloader/]);
  await expect(page.getByRole("button", { name: "Move Blue in Green up" })).toBeDisabled();
  await page.reload();
  await expect(tracks(page)).toHaveText([/Blue in Green/, /So What/, /All Blues/, /Freddie Freeloader/]);
});

test("remove updates the total", async ({ page }) => {
  await page.getByRole("button", { name: "Remove So What" }).click();
  await expect(tracks(page)).toHaveCount(3);
  await expect(total(page)).toHaveText("Total 26:59");
  await page.reload();
  await expect(tracks(page)).toHaveCount(3);
  await expect(total(page)).toHaveText("Total 26:59");
});

test("repeat toggle reports aria-pressed and is remembered", async ({ page }) => {
  const repeat = page.getByRole("button", { name: "Repeat" });
  await expect(repeat).toHaveAttribute("aria-pressed", "false");
  await repeat.click();
  await expect(repeat).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await expect(page.getByRole("button", { name: "Repeat" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Repeat" }).click();
  await expect(page.getByRole("button", { name: "Repeat" })).toHaveAttribute("aria-pressed", "false");
});
