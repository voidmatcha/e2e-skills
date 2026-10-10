import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Flashcards", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Study Spanish basics", exact: true })).toBeVisible();
});

const answerCard = async (page, { cardId, learned, buttonName }) => {
  const update = page.waitForRequest((request) => (
    request.method() === "PATCH"
    && request.url().endsWith(`/api/cards/${cardId}`)
    && request.postDataJSON().learned === learned
  ));

  await page.getByRole("button", { name: buttonName, exact: true }).click();
  await update;
};

test("reviews Spanish basics cards and persists learned progress", async ({ page }) => {
  await expect(page.getByText("3 cards · 1 learned")).toBeVisible();

  await page.getByRole("button", { name: "Study Spanish basics", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Studying Spanish basics", exact: true })).toBeVisible();
  await expect(page.getByText("Card 1 of 3")).toBeVisible();
  await expect(page.getByText("hola")).toBeVisible();

  await page.getByRole("button", { name: "Flip", exact: true }).click();
  await expect(page.getByText("hello")).toBeVisible();

  await answerCard(page, { cardId: 1, learned: false, buttonName: "Again" });
  await expect(page.getByText("Card 2 of 3")).toBeVisible();
  await expect(page.getByText("gracias")).toBeVisible();

  await answerCard(page, { cardId: 2, learned: true, buttonName: "Got it" });
  await expect(page.getByText("Card 3 of 3")).toBeVisible();
  await expect(page.getByText("adiós")).toBeVisible();

  await page.getByRole("button", { name: "Flip", exact: true }).click();
  await expect(page.getByText("goodbye")).toBeVisible();

  await answerCard(page, { cardId: 3, learned: true, buttonName: "Got it" });
  await expect(page.getByText("Session done")).toBeVisible();
  await expect(page.getByText("All 3 cards reviewed")).toBeVisible();
  await expect(page.getByText("3 cards · 2 learned")).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: "Flashcards", exact: true })).toBeVisible();
  await expect(page.getByText("3 cards · 2 learned")).toBeVisible();

  await page.getByRole("button", { name: "Study Spanish basics", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Studying Spanish basics", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Back to decks", exact: true }).click();
  // JUSTIFIED: the close action's contract is the hidden Study section; once hidden, its role content leaves the accessibility tree.
  await expect(page.locator("#fc-study")).toHaveAttribute("hidden", "");
});

test("reviews Capitals cards and keeps Again answers unlearned", async ({ page }) => {
  await expect(page.getByText("2 cards · 0 learned")).toBeVisible();

  await page.getByRole("button", { name: "Study Capitals", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Studying Capitals", exact: true })).toBeVisible();
  await expect(page.getByText("Card 1 of 2")).toBeVisible();
  await expect(page.getByText("Norway")).toBeVisible();

  await page.getByRole("button", { name: "Flip", exact: true }).click();
  await expect(page.getByText("Oslo")).toBeVisible();

  await answerCard(page, { cardId: 4, learned: false, buttonName: "Again" });
  await expect(page.getByText("Card 2 of 2")).toBeVisible();
  await expect(page.getByText("Peru")).toBeVisible();

  await page.getByRole("button", { name: "Flip", exact: true }).click();
  await expect(page.getByText("Lima")).toBeVisible();

  await answerCard(page, { cardId: 5, learned: true, buttonName: "Got it" });
  await expect(page.getByText("Session done")).toBeVisible();
  await expect(page.getByText("All 2 cards reviewed")).toBeVisible();
  await expect(page.getByText("2 cards · 1 learned")).toBeVisible();
});
