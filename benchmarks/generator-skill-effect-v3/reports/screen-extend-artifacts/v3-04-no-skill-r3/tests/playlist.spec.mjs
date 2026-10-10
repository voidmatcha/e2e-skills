import { expect, test } from "@playwright/test";

const SEED = ["Blue in Green", "So What", "Freddie Freeloader", "All Blues"];

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.locator("#pl-tracks .title")).toHaveText(SEED);
});

const titles = (page) => page.locator("#pl-tracks .title");

test("lists the seeded tracks with lengths and total", async ({ page }) => {
  await expect(page.locator("#pl-tracks .length")).toHaveText(["5:37", "9:22", "9:49", "11:33"]);
  await expect(page.locator("#pl-total")).toHaveText("Total 36:21");
});

test("Play shows the Now playing panel and Stop hides it", async ({ page }) => {
  const panel = page.locator("#pl-now");
  await expect(panel).toBeHidden();
  await page.getByRole("button", { name: "Play So What" }).click();
  await expect(panel).toBeVisible();
  await expect(page.locator("#pl-now-title")).toHaveText("So What");
  await page.getByRole("button", { name: "Stop" }).click();
  await expect(panel).toBeHidden();
});

test("Move up and Move down reorder tracks and persist across reload", async ({ page }) => {
  await page.getByRole("button", { name: "Move So What up" }).click();
  await expect(titles(page)).toHaveText(["So What", "Blue in Green", "Freddie Freeloader", "All Blues"]);
  await page.getByRole("button", { name: "Move All Blues up" }).click();
  await page.getByRole("button", { name: "Move Blue in Green down" }).click();
  await expect(titles(page)).toHaveText(["So What", "All Blues", "Blue in Green", "Freddie Freeloader"]);

  await page.reload();
  await expect(titles(page)).toHaveText(["So What", "All Blues", "Blue in Green", "Freddie Freeloader"]);
});

test("first track cannot move up and last cannot move down", async ({ page }) => {
  await expect(page.getByRole("button", { name: "Move Blue in Green up" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move All Blues down" })).toBeDisabled();
});

test("Remove deletes a track and the total follows", async ({ page }) => {
  await page.getByRole("button", { name: "Remove So What" }).click();
  await expect(titles(page)).toHaveText(["Blue in Green", "Freddie Freeloader", "All Blues"]);
  await expect(page.locator("#pl-total")).toHaveText("Total 26:59");

  await page.reload();
  await expect(titles(page)).toHaveText(["Blue in Green", "Freddie Freeloader", "All Blues"]);
  await expect(page.locator("#pl-total")).toHaveText("Total 26:59");
});

test("Repeat toggle reports aria-pressed and is remembered across reload", async ({ page }) => {
  const repeat = page.getByRole("button", { name: "Repeat" });
  await expect(repeat).toHaveAttribute("aria-pressed", "false");
  await repeat.click();
  await expect(repeat).toHaveAttribute("aria-pressed", "true");

  await page.reload();
  await expect(repeat).toHaveAttribute("aria-pressed", "true");

  await repeat.click();
  await expect(repeat).toHaveAttribute("aria-pressed", "false");
  await page.reload();
  await expect(repeat).toHaveAttribute("aria-pressed", "false");
});
