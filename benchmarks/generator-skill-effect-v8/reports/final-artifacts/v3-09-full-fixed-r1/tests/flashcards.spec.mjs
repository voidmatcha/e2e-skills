import { expect, test } from "@playwright/test";

const deck = (page, name) =>
  page.locator("article").filter({ has: page.getByRole("heading", { name, exact: true }) });

const answerCard = async (page, cardId, learned) => {
  const button = page.getByRole("button", { name: learned ? "Got it" : "Again", exact: true });
  const requestPromise = page.waitForRequest((request) => {
    if (request.method() !== "PATCH" || !request.url().endsWith(`/api/cards/${cardId}`)) {
      return false;
    }

    return request.postDataJSON().learned === learned;
  });

  await button.click();
  await requestPromise;
};

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("studies Spanish basics and updates learned progress", async ({ page }) => {
  const studyPanel = page.getByRole("region", { name: "Study", exact: true });
  const spanishDeck = deck(page, "Spanish basics");

  await expect(spanishDeck.getByText("3 cards · 1 learned")).toBeVisible();
  await page.getByRole("button", { name: "Study Spanish basics", exact: true }).click();

  await expect(studyPanel.getByRole("heading", { name: "Studying Spanish basics", exact: true })).toBeVisible();
  await expect(studyPanel.getByText("Card 1 of 3")).toBeVisible();
  await expect(studyPanel.getByText("hola")).toBeVisible();

  await page.getByRole("button", { name: "Flip", exact: true }).click();
  await expect(studyPanel.getByText("hello")).toBeVisible();

  await answerCard(page, 1, true);
  await expect(studyPanel.getByText("Card 2 of 3")).toBeVisible();
  await expect(studyPanel.getByText("gracias")).toBeVisible();
  await expect(spanishDeck.getByText("3 cards · 2 learned")).toBeVisible();

  await answerCard(page, 2, false);
  await expect(studyPanel.getByText("Card 3 of 3")).toBeVisible();
  await expect(studyPanel.getByText("adiós")).toBeVisible();
  await expect(spanishDeck.getByText("3 cards · 1 learned")).toBeVisible();

  await answerCard(page, 3, true);
  await expect(studyPanel.getByText("Session done")).toBeVisible();
  await expect(studyPanel.getByText("All 3 cards reviewed")).toBeVisible();
  await expect(spanishDeck.getByText("3 cards · 2 learned")).toBeVisible();

  await page.getByRole("button", { name: "Back to decks", exact: true }).click();
  await expect(studyPanel).toBeHidden();
});

test("studies Capitals through the final reviewed state", async ({ page }) => {
  const studyPanel = page.getByRole("region", { name: "Study", exact: true });
  const capitalsDeck = deck(page, "Capitals");

  await expect(capitalsDeck.getByText("2 cards · 0 learned")).toBeVisible();
  await page.getByRole("button", { name: "Study Capitals", exact: true }).click();

  await expect(studyPanel.getByRole("heading", { name: "Studying Capitals", exact: true })).toBeVisible();
  await expect(studyPanel.getByText("Card 1 of 2")).toBeVisible();
  await expect(studyPanel.getByText("Norway")).toBeVisible();

  await page.getByRole("button", { name: "Flip", exact: true }).click();
  await expect(studyPanel.getByText("Oslo")).toBeVisible();

  await answerCard(page, 4, false);
  await expect(studyPanel.getByText("Card 2 of 2")).toBeVisible();
  await expect(studyPanel.getByText("Peru")).toBeVisible();
  await expect(capitalsDeck.getByText("2 cards · 0 learned")).toBeVisible();

  await page.getByRole("button", { name: "Flip", exact: true }).click();
  await expect(studyPanel.getByText("Lima")).toBeVisible();

  await answerCard(page, 5, true);
  await expect(studyPanel.getByText("Session done")).toBeVisible();
  await expect(studyPanel.getByText("All 2 cards reviewed")).toBeVisible();
  await expect(capitalsDeck.getByText("2 cards · 1 learned")).toBeVisible();
});

test("persists learned state after reload", async ({ page }) => {
  const capitalsDeck = deck(page, "Capitals");

  await page.getByRole("button", { name: "Study Capitals", exact: true }).click();
  await answerCard(page, 4, true);

  await page.reload();

  await expect(capitalsDeck.getByText("2 cards · 1 learned")).toBeVisible();
});
