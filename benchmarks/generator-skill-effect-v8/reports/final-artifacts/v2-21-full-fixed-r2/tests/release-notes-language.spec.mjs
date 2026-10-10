import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test.afterEach(async ({ request }) => {
  await request.post("/api/reset");
});

const expectEnglishReleaseNotes = async (page) => {
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByText("Language", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Release notes", exact: true })).toBeVisible();
  await expect(page.getByText("Published: October 5, 2026")).toBeVisible();
  await expect(page.getByText("Version 3.2 adds offline mode and faster sync.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Subscribe to updates", exact: true })).toBeVisible();
};

const expectGermanReleaseNotes = async (page) => {
  await expect(page.locator("html")).toHaveAttribute("lang", "de");
  await expect(page.getByText("Sprache", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Versionshinweise", exact: true })).toBeVisible();
  await expect(page.getByText("Veröffentlicht: 5. Oktober 2026")).toBeVisible();
  await expect(page.getByText("Version 3.2 bringt einen Offline-Modus und schnellere Synchronisierung.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Updates abonnieren", exact: true })).toBeVisible();
};

test("switches release notes language and persists the choice after reload", async ({ page }) => {
  await page.goto("/");
  await expectEnglishReleaseNotes(page);

  const languageSwitcher = page.getByLabel(/^(Language|Sprache)$/);
  const germanUpdate = page.waitForResponse(
    (response) => response.url().endsWith("/api/language") && response.request().method() === "PUT" && response.ok(),
  );
  await languageSwitcher.selectOption("de");
  await germanUpdate;

  await expectGermanReleaseNotes(page);

  await page.reload();
  await expectGermanReleaseNotes(page);

  const englishUpdate = page.waitForResponse(
    (response) => response.url().endsWith("/api/language") && response.request().method() === "PUT" && response.ok(),
  );
  await languageSwitcher.selectOption("en");
  await englishUpdate;

  await expectEnglishReleaseNotes(page);
});
