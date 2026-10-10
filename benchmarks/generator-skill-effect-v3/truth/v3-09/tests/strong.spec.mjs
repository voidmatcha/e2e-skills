import { expect, test } from "@playwright/test";

const panel = (page) => page.getByRole("region", { name: "Study" });
const deck = (page, name) => page.getByRole("article").filter({ has: page.getByRole("heading", { name }) });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(deck(page, "Spanish basics")).toContainText("3 cards · 1 learned");
});

test("study walks through the deck with progress, flip and session done", async ({ page }) => {
  await expect(panel(page)).toBeHidden();
  await page.getByRole("button", { name: "Study Capitals" }).click();
  await expect(panel(page).getByRole("heading")).toHaveText("Studying Capitals");
  await expect(panel(page)).toContainText("Card 1 of 2");
  await expect(panel(page)).toContainText("Norway");
  await expect(panel(page).getByText("Oslo")).toBeHidden();
  await page.getByRole("button", { name: "Flip" }).click();
  await expect(panel(page).getByText("Oslo")).toBeVisible();
  await page.getByRole("button", { name: "Got it" }).click();
  await expect(panel(page)).toContainText("Card 2 of 2");
  await expect(panel(page)).toContainText("Peru");
  await expect(panel(page).getByText("Lima")).toBeHidden();
  await page.getByRole("button", { name: "Again" }).click();
  await expect(panel(page)).toContainText("Session done");
  await expect(panel(page)).toContainText("All 2 cards reviewed");
  await expect(deck(page, "Capitals")).toContainText("2 cards · 1 learned");
  await page.getByRole("button", { name: "Back to decks" }).click();
  await expect(panel(page)).toBeHidden();
});

test("got it and again persist their learned state", async ({ page }) => {
  await page.getByRole("button", { name: "Study Spanish basics" }).click();
  await page.getByRole("button", { name: "Got it" }).click();
  await page.getByRole("button", { name: "Again" }).click();
  await page.getByRole("button", { name: "Got it" }).click();
  await expect(panel(page)).toContainText("Session done");
  await expect(deck(page, "Spanish basics")).toContainText("3 cards · 2 learned");
  await page.reload();
  await expect(deck(page, "Spanish basics")).toContainText("3 cards · 2 learned");
  await expect(deck(page, "Capitals")).toContainText("2 cards · 0 learned");
});
