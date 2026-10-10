import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
});

test.afterEach(async ({ request }) => {
  await request.post("/api/reset");
});

const expectEnglish = async (page) => {
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { name: "Release notes" })).toBeVisible();
  await expect(page.getByLabel("Language")).toBeVisible();
  await expect(page.getByText("Version 3.2 adds offline mode and faster sync.")).toBeVisible();
  await expect(page.getByText("Published: October 5, 2026")).toBeVisible();
  await expect(page.getByRole("button", { name: "Subscribe to updates" })).toBeVisible();
};

const expectGerman = async (page) => {
  await expect(page.locator("html")).toHaveAttribute("lang", "de");
  await expect(page.getByRole("heading", { name: "Versionshinweise" })).toBeVisible();
  await expect(page.getByLabel("Sprache")).toBeVisible();
  await expect(page.getByText("Version 3.2 bringt einen Offline-Modus und schnellere Synchronisierung.")).toBeVisible();
  await expect(page.getByText("Veröffentlicht: 5. Oktober 2026")).toBeVisible();
  await expect(page.getByRole("button", { name: "Updates abonnieren" })).toBeVisible();
};

test("defaults to English", async ({ page }) => {
  await page.goto("/");
  await expectEnglish(page);
  await expect(page.getByLabel("Language")).toHaveValue("en");
});

test("choosing Deutsch translates the page", async ({ page }) => {
  await page.goto("/");
  await expectEnglish(page);
  await page.getByLabel("Language").selectOption({ label: "Deutsch" });
  await expectGerman(page);
  await expect(page.getByLabel("Sprache")).toHaveValue("de");
});

test("choosing English switches back from German", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Language").selectOption({ label: "Deutsch" });
  await expectGerman(page);
  await page.getByLabel("Sprache").selectOption({ label: "English" });
  await expectEnglish(page);
});

test("the chosen language survives a reload", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Language").selectOption({ label: "Deutsch" });
  await expectGerman(page);
  await page.reload();
  await expectGerman(page);
  await expect(page.getByLabel("Sprache")).toHaveValue("de");
});

test("the choice is stored on the server", async ({ page, request }) => {
  await page.goto("/");
  await page.getByLabel("Language").selectOption({ label: "Deutsch" });
  await expectGerman(page);
  expect(await (await request.get("/api/language")).json()).toEqual({ language: "de" });

  await page.getByLabel("Sprache").selectOption({ label: "English" });
  await expectEnglish(page);
  expect(await (await request.get("/api/language")).json()).toEqual({ language: "en" });
});
