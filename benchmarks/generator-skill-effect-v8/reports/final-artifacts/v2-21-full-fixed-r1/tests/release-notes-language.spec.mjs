import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("switches between English and German release notes", async ({ page }) => {
  await page.goto("/");

  const germanUpdate = page.waitForRequest((request) => request.method() === "PUT" && request.url().endsWith("/api/language"));
  await page.getByLabel("Language").selectOption("de");
  const germanRequest = await germanUpdate;

  expect(germanRequest.postDataJSON()).toEqual({ language: "de" });
  await expect(page.getByRole("heading", { name: "Versionshinweise", exact: true })).toBeVisible();
  await expect(page.getByLabel("Sprache")).toHaveValue("de");
  await expect(page.locator("html")).toHaveAttribute("lang", "de");
  await expect(page.getByText("Veröffentlicht: 5. Oktober 2026")).toBeVisible();
  await expect(page.getByText("Version 3.2 bringt einen Offline-Modus und schnellere Synchronisierung.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Updates abonnieren", exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: "Versionshinweise", exact: true })).toBeVisible();
  await expect(page.getByLabel("Sprache")).toHaveValue("de");
  await expect(page.locator("html")).toHaveAttribute("lang", "de");

  const englishUpdate = page.waitForRequest((request) => request.method() === "PUT" && request.url().endsWith("/api/language"));
  await page.getByLabel("Sprache").selectOption("en");
  const englishRequest = await englishUpdate;

  expect(englishRequest.postDataJSON()).toEqual({ language: "en" });
  await expect(page.getByRole("heading", { name: "Release notes", exact: true })).toBeVisible();
  await expect(page.getByLabel("Language")).toHaveValue("en");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByText("Published: October 5, 2026")).toBeVisible();
  await expect(page.getByText("Version 3.2 adds offline mode and faster sync.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Subscribe to updates", exact: true })).toBeVisible();
});
