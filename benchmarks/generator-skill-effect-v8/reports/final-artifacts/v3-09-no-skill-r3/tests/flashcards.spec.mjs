import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

const deck = (page, name) =>
  page.locator(".deck").filter({ has: page.getByRole("heading", { name }) });

test("shows both decks with their starting learned counts", async ({ page }) => {
  await expect(deck(page, "Spanish basics")).toContainText("3 cards · 1 learned");
  await expect(deck(page, "Capitals")).toContainText("2 cards · 0 learned");
});

test("studies Spanish basics and persists learned state after reload", async ({ page }) => {
  await deck(page, "Spanish basics").getByRole("button", { name: "Study" }).click();

  await expect(page.getByRole("heading", { name: "Studying Spanish basics" })).toBeVisible();
  await expect(page.getByText("Card 1 of 3")).toBeVisible();
  await expect(page.getByText("hola")).toBeVisible();

  await page.getByRole("button", { name: "Flip" }).click();
  await expect(page.getByText("hello")).toBeVisible();

  await page.getByRole("button", { name: "Got it" }).click();
  await expect(page.getByText("Card 2 of 3")).toBeVisible();
  await expect(page.getByText("gracias")).toBeVisible();

  await page.getByRole("button", { name: "Flip" }).click();
  await expect(page.getByText("thank you")).toBeVisible();

  await page.getByRole("button", { name: "Again" }).click();
  await expect(page.getByText("Card 3 of 3")).toBeVisible();
  await expect(page.getByText("adiós")).toBeVisible();

  await page.getByRole("button", { name: "Flip" }).click();
  await expect(page.getByText("goodbye")).toBeVisible();

  await page.getByRole("button", { name: "Got it" }).click();
  await expect(page.getByText("Session done")).toBeVisible();
  await expect(page.getByText("All 3 cards reviewed")).toBeVisible();
  await expect(deck(page, "Spanish basics")).toContainText("3 cards · 2 learned");

  await page.reload();
  await expect(deck(page, "Spanish basics")).toContainText("3 cards · 2 learned");
});

test("studies Capitals, updates progress, and closes the study panel", async ({ page }) => {
  await deck(page, "Capitals").getByRole("button", { name: "Study" }).click();

  await expect(page.getByRole("heading", { name: "Studying Capitals" })).toBeVisible();
  await expect(page.getByText("Card 1 of 2")).toBeVisible();
  await expect(page.getByText("Norway")).toBeVisible();

  await page.getByRole("button", { name: "Flip" }).click();
  await expect(page.getByText("Oslo")).toBeVisible();

  await page.getByRole("button", { name: "Again" }).click();
  await expect(page.getByText("Card 2 of 2")).toBeVisible();
  await expect(page.getByText("Peru")).toBeVisible();

  await page.getByRole("button", { name: "Flip" }).click();
  await expect(page.getByText("Lima")).toBeVisible();

  await page.getByRole("button", { name: "Got it" }).click();
  await expect(page.getByText("Session done")).toBeVisible();
  await expect(page.getByText("All 2 cards reviewed")).toBeVisible();
  await expect(deck(page, "Capitals")).toContainText("2 cards · 1 learned");

  await page.reload();
  await expect(deck(page, "Capitals")).toContainText("2 cards · 1 learned");

  await deck(page, "Capitals").getByRole("button", { name: "Study" }).click();
  await expect(page.getByRole("heading", { name: "Studying Capitals" })).toBeVisible();

  await page.getByRole("button", { name: "Back to decks" }).click();
  await expect(page.getByRole("heading", { name: "Studying Capitals" })).toBeHidden();
});
