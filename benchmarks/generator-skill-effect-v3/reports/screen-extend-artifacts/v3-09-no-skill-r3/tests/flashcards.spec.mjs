import { expect, test } from "@playwright/test";

const deckCard = (page, name) =>
  page.locator("article.deck").filter({ has: page.getByRole("heading", { name }) });

test.beforeEach(async ({ page, request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBeTruthy();
  await page.goto("/");
});

test("lists both decks with their learned counts", async ({ page }) => {
  await expect(deckCard(page, "Spanish basics").locator(".deck-line")).toHaveText("3 cards · 1 learned");
  await expect(deckCard(page, "Capitals").locator(".deck-line")).toHaveText("2 cards · 0 learned");
  await expect(page.getByRole("region", { name: "Study" })).toBeHidden();
});

test("study opens the panel on the first card", async ({ page }) => {
  await page.getByRole("button", { name: "Study Spanish basics" }).click();
  await expect(page.getByRole("heading", { name: "Studying Spanish basics" })).toBeVisible();
  await expect(page.getByText("hola", { exact: true })).toBeVisible();
  await expect(page.getByText("Card 1 of 3")).toBeVisible();
  await expect(page.getByText("hello", { exact: true })).toBeHidden();
});

test("flip reveals the back of the card", async ({ page }) => {
  await page.getByRole("button", { name: "Study Capitals" }).click();
  await expect(page.getByText("Norway", { exact: true })).toBeVisible();
  await expect(page.getByText("Oslo", { exact: true })).toBeHidden();
  await page.getByRole("button", { name: "Flip" }).click();
  await expect(page.getByText("Oslo", { exact: true })).toBeVisible();
});

test("answering advances the card and the progress line", async ({ page }) => {
  await page.getByRole("button", { name: "Study Spanish basics" }).click();
  await page.getByRole("button", { name: "Got it" }).click();
  await expect(page.getByText("Card 2 of 3")).toBeVisible();
  await expect(page.getByText("gracias", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Again" }).click();
  await expect(page.getByText("Card 3 of 3")).toBeVisible();
  await expect(page.getByText("adiós", { exact: true })).toBeVisible();
  // the back is hidden again on the new card
  await expect(page.locator("#fc-back")).toBeHidden();
});

test("finishing a deck shows the summary and updates the learned count", async ({ page }) => {
  await page.getByRole("button", { name: "Study Capitals" }).click();
  await page.getByRole("button", { name: "Got it" }).click();
  await expect(page.getByText("Card 2 of 2")).toBeVisible();
  await page.getByRole("button", { name: "Again" }).click();

  await expect(page.getByText("Session done")).toBeVisible();
  await expect(page.getByText("All 2 cards reviewed")).toBeVisible();
  await expect(page.getByRole("button", { name: "Got it" })).toBeHidden();
  await expect(page.getByRole("button", { name: "Flip" })).toBeHidden();
  await expect(deckCard(page, "Capitals").locator(".deck-line")).toHaveText("2 cards · 1 learned");
});

test("Again unlearns an already learned card", async ({ page }) => {
  await page.getByRole("button", { name: "Study Spanish basics" }).click();
  await page.getByRole("button", { name: "Again" }).click(); // hola
  await page.getByRole("button", { name: "Again" }).click(); // gracias (was learned)
  await page.getByRole("button", { name: "Again" }).click(); // adiós
  await expect(page.getByText("All 3 cards reviewed")).toBeVisible();
  await expect(deckCard(page, "Spanish basics").locator(".deck-line")).toHaveText("3 cards · 0 learned");
});

test("learned state survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Study Capitals" }).click();
  await page.getByRole("button", { name: "Got it" }).click();
  await page.getByRole("button", { name: "Got it" }).click();
  await expect(page.getByText("All 2 cards reviewed")).toBeVisible();
  await expect(deckCard(page, "Capitals").locator(".deck-line")).toHaveText("2 cards · 2 learned");

  await page.reload();
  await expect(deckCard(page, "Capitals").locator(".deck-line")).toHaveText("2 cards · 2 learned");
  await expect(deckCard(page, "Spanish basics").locator(".deck-line")).toHaveText("3 cards · 1 learned");
});

test("back to decks closes the panel", async ({ page }) => {
  await page.getByRole("button", { name: "Study Capitals" }).click();
  await expect(page.getByRole("heading", { name: "Studying Capitals" })).toBeVisible();
  await page.getByRole("button", { name: "Back to decks" }).click();
  await expect(page.getByRole("heading", { name: "Studying Capitals" })).toBeHidden();
  await expect(page.getByRole("button", { name: "Study Capitals" })).toBeVisible();
});
