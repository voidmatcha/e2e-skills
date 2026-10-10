import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
});

const switcher = (page, name) => page.getByRole("combobox", { name });

async function expectEnglish(page) {
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { name: "Release notes" })).toBeVisible();
  await expect(switcher(page, "Language")).toBeVisible();
  await expect(page.getByText("Version 3.2 adds offline mode and faster sync.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Subscribe to updates" })).toBeVisible();
  await expect(page.getByText("Published: October 5, 2026")).toBeVisible();
}

async function expectGerman(page) {
  await expect(page.locator("html")).toHaveAttribute("lang", "de");
  await expect(page.getByRole("heading", { name: "Versionshinweise" })).toBeVisible();
  await expect(switcher(page, "Sprache")).toBeVisible();
  await expect(page.getByText("Version 3.2 bringt einen Offline-Modus und schnellere Synchronisierung.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Updates abonnieren" })).toBeVisible();
  await expect(page.getByText("Veröffentlicht: 5. Oktober 2026")).toBeVisible();
}

test("defaults to English", async ({ page }) => {
  await page.goto("/");
  await expectEnglish(page);
  await expect(switcher(page, "Language")).toHaveValue("en");
});

test("choosing Deutsch translates the whole page", async ({ page }) => {
  await page.goto("/");
  await expectEnglish(page);
  await switcher(page, "Language").selectOption({ label: "Deutsch" });
  await expectGerman(page);
  await expect(switcher(page, "Sprache")).toHaveValue("de");
});

test("choosing English switches back from German", async ({ page }) => {
  await page.goto("/");
  await switcher(page, "Language").selectOption({ label: "Deutsch" });
  await expectGerman(page);
  await switcher(page, "Sprache").selectOption({ label: "English" });
  await expectEnglish(page);
  await expect(switcher(page, "Language")).toHaveValue("en");
});

test("the chosen language persists across a reload", async ({ page, request }) => {
  await page.goto("/");
  await switcher(page, "Language").selectOption({ label: "Deutsch" });
  await expectGerman(page);

  await page.reload();
  await expectGerman(page);
  await expect(switcher(page, "Sprache")).toHaveValue("de");
  expect(await (await request.get("/api/language")).json()).toEqual({ language: "de" });

  await switcher(page, "Sprache").selectOption({ label: "English" });
  await expectEnglish(page);
  await page.reload();
  await expectEnglish(page);
});
