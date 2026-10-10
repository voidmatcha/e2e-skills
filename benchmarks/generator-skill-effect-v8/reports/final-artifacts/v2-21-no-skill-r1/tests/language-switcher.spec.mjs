import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("switches release notes between English and German and persists the choice", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { name: "Release notes" })).toBeVisible();
  await expect(page.getByLabel("Language")).toHaveValue("en");
  await expect(page.getByText("Published: October 5, 2026")).toBeVisible();
  await expect(page.getByText("Version 3.2 adds offline mode and faster sync.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Subscribe to updates" })).toBeVisible();

  await page.getByLabel("Language").selectOption("de");

  await expect(page.locator("html")).toHaveAttribute("lang", "de");
  await expect(page.getByRole("heading", { name: "Versionshinweise" })).toBeVisible();
  await expect(page.getByLabel("Sprache")).toHaveValue("de");
  await expect(page.getByText("Veröffentlicht: 5. Oktober 2026")).toBeVisible();
  await expect(page.getByText("Version 3.2 bringt einen Offline-Modus und schnellere Synchronisierung.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Updates abonnieren" })).toBeVisible();

  await page.reload();

  await expect(page.locator("html")).toHaveAttribute("lang", "de");
  await expect(page.getByRole("heading", { name: "Versionshinweise" })).toBeVisible();
  await expect(page.getByLabel("Sprache")).toHaveValue("de");
  await expect(page.getByText("Veröffentlicht: 5. Oktober 2026")).toBeVisible();
  await expect(page.getByText("Version 3.2 bringt einen Offline-Modus und schnellere Synchronisierung.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Updates abonnieren" })).toBeVisible();

  await page.getByLabel("Sprache").selectOption("en");

  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { name: "Release notes" })).toBeVisible();
  await expect(page.getByLabel("Language")).toHaveValue("en");
  await expect(page.getByText("Published: October 5, 2026")).toBeVisible();
  await expect(page.getByText("Version 3.2 adds offline mode and faster sync.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Subscribe to updates" })).toBeVisible();
});
