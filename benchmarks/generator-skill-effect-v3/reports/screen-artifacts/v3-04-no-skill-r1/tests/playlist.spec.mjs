import { expect, test } from "@playwright/test";

const SEEDED = ["Blue in Green", "So What", "Freddie Freeloader", "All Blues"];

test.beforeEach(async ({ page, request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.locator("#pl-tracks .title")).toHaveText(SEEDED);
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

  await page.getByRole("button", { name: "Play All Blues" }).click();
  await expect(page.locator("#pl-now-title")).toHaveText("All Blues");

  await page.getByRole("button", { name: "Stop" }).click();
  await expect(panel).toBeHidden();
});

test("Move up reorders tracks and survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Move So What up" }).click();
  const expected = ["So What", "Blue in Green", "Freddie Freeloader", "All Blues"];
  await expect(titles(page)).toHaveText(expected);

  await page.reload();
  await expect(titles(page)).toHaveText(expected);
});

test("Move down reorders tracks and survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Move Freddie Freeloader down" }).click();
  const expected = ["Blue in Green", "So What", "All Blues", "Freddie Freeloader"];
  await expect(titles(page)).toHaveText(expected);

  await page.reload();
  await expect(titles(page)).toHaveText(expected);
});

test("first track cannot move up and last cannot move down", async ({ page }) => {
  await expect(page.getByRole("button", { name: "Move Blue in Green up" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move All Blues down" })).toBeDisabled();
});

test("Remove deletes a track and the total follows", async ({ page }) => {
  await expect(page.locator("#pl-total")).toHaveText("Total 36:21");
  await page.getByRole("button", { name: "Remove So What" }).click();
  await expect(titles(page)).toHaveText(["Blue in Green", "Freddie Freeloader", "All Blues"]);
  // 36:21 - 9:22 = 26:59
  await expect(page.locator("#pl-total")).toHaveText("Total 26:59");
});

test("removing the playing track hides the Now playing panel", async ({ page }) => {
  await page.getByRole("button", { name: "Play So What" }).click();
  await expect(page.locator("#pl-now")).toBeVisible();
  await page.getByRole("button", { name: "Remove So What" }).click();
  await expect(page.locator("#pl-now")).toBeHidden();
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
