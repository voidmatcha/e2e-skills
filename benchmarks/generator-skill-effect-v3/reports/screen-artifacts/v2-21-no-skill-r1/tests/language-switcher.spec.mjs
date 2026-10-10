import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Release notes" })).toBeVisible();
});

async function expectEnglish(page) {
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { name: "Release notes" })).toBeVisible();
  await expect(page.getByLabel("Language")).toHaveValue("en");
  await expect(page.getByText("Version 3.2 adds offline mode and faster sync.")).toBeVisible();
  await expect(page.getByText("Published: October 5, 2026")).toBeVisible();
  await expect(page.getByRole("button", { name: "Subscribe to updates" })).toBeVisible();
}

async function expectGerman(page) {
  await expect(page.locator("html")).toHaveAttribute("lang", "de");
  await expect(page.getByRole("heading", { name: "Versionshinweise" })).toBeVisible();
  await expect(page.getByLabel("Sprache")).toHaveValue("de");
  await expect(page.getByText("Version 3.2 bringt einen Offline-Modus und schnellere Synchronisierung.")).toBeVisible();
  await expect(page.getByText("Veröffentlicht: 5. Oktober 2026")).toBeVisible();
  await expect(page.getByRole("button", { name: "Updates abonnieren" })).toBeVisible();
}

test("defaults to English", async ({ page }) => {
  await expectEnglish(page);
});

test("choosing Deutsch translates the page", async ({ page }) => {
  await page.getByLabel("Language").selectOption({ label: "Deutsch" });
  await expectGerman(page);
});

test("choosing English switches back from German", async ({ page }) => {
  await page.getByLabel("Language").selectOption({ label: "Deutsch" });
  await expectGerman(page);
  await page.getByLabel("Sprache").selectOption({ label: "English" });
  await expectEnglish(page);
});

test("the chosen language persists across a reload", async ({ page }) => {
  await page.getByLabel("Language").selectOption({ label: "Deutsch" });
  await expectGerman(page);
  await page.reload();
  await expectGerman(page);

  await page.getByLabel("Sprache").selectOption({ label: "English" });
  await expectEnglish(page);
  await page.reload();
  await expectEnglish(page);
});
