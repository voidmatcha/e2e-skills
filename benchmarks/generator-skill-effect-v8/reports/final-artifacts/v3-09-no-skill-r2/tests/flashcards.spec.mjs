import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const deck = (page, name) =>
  page.locator("article.deck").filter({ has: page.getByRole("heading", { name }) });

test("studies Spanish basics and persists learned cards after reload", async ({ page }) => {
  await page.goto("/");

  const spanish = deck(page, "Spanish basics");
  await expect(spanish).toContainText("3 cards · 1 learned");

  await page.getByRole("button", { name: "Study Spanish basics" }).click();
  await expect(page.getByRole("heading", { name: "Studying Spanish basics" })).toBeVisible();
  await expect(page.locator("#fc-progress")).toHaveText("Card 1 of 3");
  await expect(page.locator("#fc-front")).toHaveText("hola");

  await page.getByRole("button", { name: "Flip" }).click();
  await expect(page.locator("#fc-back")).toHaveText("hello");

  await page.getByRole("button", { name: "Got it" }).click();
  await expect(page.locator("#fc-progress")).toHaveText("Card 2 of 3");
  await expect(page.locator("#fc-front")).toHaveText("gracias");

  await page.getByRole("button", { name: "Again" }).click();
  await expect(page.locator("#fc-progress")).toHaveText("Card 3 of 3");
  await expect(page.locator("#fc-front")).toHaveText("adiós");

  await page.getByRole("button", { name: "Got it" }).click();
  await expect(page.locator("#fc-done")).toHaveText("Session done");
  await expect(page.locator("#fc-progress")).toHaveText("All 3 cards reviewed");
  await expect(spanish).toContainText("3 cards · 2 learned");

  await page.reload();
  await expect(deck(page, "Spanish basics")).toContainText("3 cards · 2 learned");
});

test("studies Capitals, leaves cards unlearned, and returns to deck list", async ({ page }) => {
  await page.goto("/");

  const capitals = deck(page, "Capitals");
  await expect(capitals).toContainText("2 cards · 0 learned");

  await page.getByRole("button", { name: "Study Capitals" }).click();
  await expect(page.getByRole("heading", { name: "Studying Capitals" })).toBeVisible();
  await expect(page.locator("#fc-progress")).toHaveText("Card 1 of 2");
  await expect(page.locator("#fc-front")).toHaveText("Norway");

  await page.getByRole("button", { name: "Flip" }).click();
  await expect(page.locator("#fc-back")).toHaveText("Oslo");

  await page.getByRole("button", { name: "Again" }).click();
  await expect(page.locator("#fc-progress")).toHaveText("Card 2 of 2");
  await expect(page.locator("#fc-front")).toHaveText("Peru");

  await page.getByRole("button", { name: "Flip" }).click();
  await expect(page.locator("#fc-back")).toHaveText("Lima");

  await page.getByRole("button", { name: "Again" }).click();
  await expect(page.locator("#fc-done")).toHaveText("Session done");
  await expect(page.locator("#fc-progress")).toHaveText("All 2 cards reviewed");
  await expect(capitals).toContainText("2 cards · 0 learned");

  await page.getByRole("button", { name: "Back to decks" }).click();
  await expect(page.getByRole("region", { name: "Study" })).toBeHidden();
  await expect(page.getByRole("heading", { name: "Studying Capitals" })).toBeHidden();
});
