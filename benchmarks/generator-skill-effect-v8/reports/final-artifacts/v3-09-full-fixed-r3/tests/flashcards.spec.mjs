import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

const deck = (page, name) =>
  page.getByRole("article").filter({
    has: page.getByRole("heading", { name, exact: true }),
  });

const answerCard = async (page, buttonName, cardId, learned) => {
  const update = page.waitForRequest((request) => {
    if (request.method() !== "PATCH") return false;
    if (!request.url().endsWith(`/api/cards/${cardId}`)) return false;
    return request.postDataJSON().learned === learned;
  });

  await page.getByRole("button", { name: buttonName, exact: true }).click();
  await update;
};

test("shows both decks and closes the study panel", async ({ page }) => {
  await expect(deck(page, "Spanish basics").getByText("3 cards · 1 learned")).toBeVisible();
  await expect(deck(page, "Capitals").getByText("2 cards · 0 learned")).toBeVisible();

  const studyPanel = page.getByRole("region", { name: "Study", exact: true, includeHidden: true });

  await deck(page, "Capitals").getByRole("button", { name: "Study Capitals", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Studying Capitals", exact: true })).toBeVisible();
  await expect(page.getByText("Norway")).toBeVisible();
  await expect(page.getByText("Card 1 of 2")).toBeVisible();

  await page.getByRole("button", { name: "Back to decks", exact: true }).click();
  await expect(studyPanel).toHaveAttribute("hidden", "");
});

test("studies Spanish basics and persists learned cards after reload", async ({ page }) => {
  await deck(page, "Spanish basics").getByRole("button", { name: "Study Spanish basics", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Studying Spanish basics", exact: true })).toBeVisible();
  await expect(page.getByText("hola")).toBeVisible();
  await expect(page.getByText("Card 1 of 3")).toBeVisible();

  await page.getByRole("button", { name: "Flip", exact: true }).click();
  await expect(page.getByText("hello")).toBeVisible();

  await answerCard(page, "Got it", 1, true);
  await expect(page.getByText("gracias")).toBeVisible();
  await expect(page.getByText("Card 2 of 3")).toBeVisible();

  await page.getByRole("button", { name: "Flip", exact: true }).click();
  await expect(page.getByText("thank you")).toBeVisible();

  await answerCard(page, "Again", 2, false);
  await expect(page.getByText("adiós")).toBeVisible();
  await expect(page.getByText("Card 3 of 3")).toBeVisible();

  await answerCard(page, "Got it", 3, true);
  await expect(page.getByText("Session done")).toBeVisible();
  await expect(page.getByText("All 3 cards reviewed")).toBeVisible();
  await expect(deck(page, "Spanish basics").getByText("3 cards · 2 learned")).toBeVisible();

  await page.reload();
  await expect(deck(page, "Spanish basics").getByText("3 cards · 2 learned")).toBeVisible();
});

test("studies Capitals and keeps cards marked Again unlearned", async ({ page }) => {
  await deck(page, "Capitals").getByRole("button", { name: "Study Capitals", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Studying Capitals", exact: true })).toBeVisible();
  await expect(page.getByText("Norway")).toBeVisible();
  await expect(page.getByText("Card 1 of 2")).toBeVisible();

  await page.getByRole("button", { name: "Flip", exact: true }).click();
  await expect(page.getByText("Oslo")).toBeVisible();

  await answerCard(page, "Again", 4, false);
  await expect(page.getByText("Peru")).toBeVisible();
  await expect(page.getByText("Card 2 of 2")).toBeVisible();

  await page.getByRole("button", { name: "Flip", exact: true }).click();
  await expect(page.getByText("Lima")).toBeVisible();

  await answerCard(page, "Got it", 5, true);
  await expect(page.getByText("Session done")).toBeVisible();
  await expect(page.getByText("All 2 cards reviewed")).toBeVisible();
  await expect(deck(page, "Capitals").getByText("2 cards · 1 learned")).toBeVisible();
});
