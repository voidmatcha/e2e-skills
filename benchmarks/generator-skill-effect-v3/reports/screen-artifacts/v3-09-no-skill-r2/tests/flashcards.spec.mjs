import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

const deck = (page, name) => page.locator("article.deck", { has: page.getByRole("heading", { name }) });
const study = (page) => page.getByRole("region", { name: "Study" });

test("shows both decks with learned counts", async ({ page }) => {
  await expect(deck(page, "Spanish basics").locator(".deck-line")).toHaveText("3 cards · 1 learned");
  await expect(deck(page, "Capitals").locator(".deck-line")).toHaveText("2 cards · 0 learned");
  await expect(study(page)).toBeHidden();
});

test("study opens the panel on the first card and flip reveals the back", async ({ page }) => {
  await page.getByRole("button", { name: "Study Spanish basics" }).click();
  const panel = study(page);
  await expect(panel.getByRole("heading", { name: "Studying Spanish basics" })).toBeVisible();
  await expect(panel.getByText("Card 1 of 3")).toBeVisible();
  await expect(panel.getByText("hola", { exact: true })).toBeVisible();
  await expect(panel.getByText("hello", { exact: true })).toBeHidden();
  await panel.getByRole("button", { name: "Flip" }).click();
  await expect(panel.getByText("hello", { exact: true })).toBeVisible();
});

test("Got it and Again advance, finish the session and update the deck line", async ({ page }) => {
  await page.getByRole("button", { name: "Study Spanish basics" }).click();
  const panel = study(page);
  await panel.getByRole("button", { name: "Got it" }).click();
  await expect(panel.getByText("Card 2 of 3")).toBeVisible();
  await expect(panel.getByText("gracias", { exact: true })).toBeVisible();
  await panel.getByRole("button", { name: "Again" }).click(); // gracias was learned; Again unlearns it
  await expect(panel.getByText("Card 3 of 3")).toBeVisible();
  await expect(panel.getByText("adiós", { exact: true })).toBeVisible();
  await panel.getByRole("button", { name: "Got it" }).click();
  await expect(panel.getByText("Session done")).toBeVisible();
  await expect(panel.getByText("All 3 cards reviewed")).toBeVisible();
  await expect(deck(page, "Spanish basics").locator(".deck-line")).toHaveText("3 cards · 2 learned");
});

test("Again leaves a card unlearned", async ({ page }) => {
  await page.getByRole("button", { name: "Study Capitals" }).click();
  const panel = study(page);
  await expect(panel.getByText("Card 1 of 2")).toBeVisible();
  await panel.getByRole("button", { name: "Again" }).click();
  await expect(panel.getByText("Card 2 of 2")).toBeVisible();
  await panel.getByRole("button", { name: "Again" }).click();
  await expect(panel.getByText("All 2 cards reviewed")).toBeVisible();
  await expect(deck(page, "Capitals").locator(".deck-line")).toHaveText("2 cards · 0 learned");
});

test("learned state survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Study Capitals" }).click();
  const panel = study(page);
  await panel.getByRole("button", { name: "Got it" }).click();
  await panel.getByRole("button", { name: "Got it" }).click();
  await expect(deck(page, "Capitals").locator(".deck-line")).toHaveText("2 cards · 2 learned");
  await page.reload();
  await expect(deck(page, "Capitals").locator(".deck-line")).toHaveText("2 cards · 2 learned");
  await expect(deck(page, "Spanish basics").locator(".deck-line")).toHaveText("3 cards · 1 learned");
});

test("Back to decks closes the panel", async ({ page }) => {
  await page.getByRole("button", { name: "Study Capitals" }).click();
  await expect(study(page)).toBeVisible();
  await study(page).getByRole("button", { name: "Back to decks" }).click();
  await expect(study(page)).toBeHidden();
});
