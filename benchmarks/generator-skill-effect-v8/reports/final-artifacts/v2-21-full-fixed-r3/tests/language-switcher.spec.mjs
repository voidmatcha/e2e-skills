import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("translates release notes to German and back to English", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: /^Release notes$/ })).toBeVisible();
  await expect(page.getByLabel("Language")).toHaveValue("en");
  await expect(page.getByText("Published: October 5, 2026")).toBeVisible();
  await expect(page.getByText("Version 3.2 adds offline mode and faster sync.")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Subscribe to updates$/ })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");

  const germanUpdate = page.waitForResponse((response) =>
    response.url().endsWith("/api/language") &&
    response.request().method() === "PUT" &&
    response.status() === 200
  );
  await page.getByLabel("Language").selectOption("de");
  await germanUpdate;

  await expect(page.getByRole("heading", { name: /^Versionshinweise$/ })).toBeVisible();
  await expect(page.getByLabel("Sprache")).toHaveValue("de");
  await expect(page.getByText("Veröffentlicht: 5. Oktober 2026")).toBeVisible();
  await expect(page.getByText("Version 3.2 bringt einen Offline-Modus und schnellere Synchronisierung.")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Updates abonnieren$/ })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "de");

  await page.reload();

  await expect(page.getByRole("heading", { name: /^Versionshinweise$/ })).toBeVisible();
  await expect(page.getByLabel("Sprache")).toHaveValue("de");
  await expect(page.getByText("Veröffentlicht: 5. Oktober 2026")).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "de");

  const englishUpdate = page.waitForResponse((response) =>
    response.url().endsWith("/api/language") &&
    response.request().method() === "PUT" &&
    response.status() === 200
  );
  await page.getByLabel("Sprache").selectOption("en");
  await englishUpdate;

  await expect(page.getByRole("heading", { name: /^Release notes$/ })).toBeVisible();
  await expect(page.getByLabel("Language")).toHaveValue("en");
  await expect(page.getByText("Published: October 5, 2026")).toBeVisible();
  await expect(page.getByText("Version 3.2 adds offline mode and faster sync.")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Subscribe to updates$/ })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});
