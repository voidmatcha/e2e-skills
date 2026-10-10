import { expect, test } from "@playwright/test";

const html = (page) => page.locator("html");

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Release notes" })).toBeVisible();
});

test("german translates every string, the lang attribute and the date", async ({ page }) => {
  await page.getByLabel("Language").selectOption("de");
  await expect(page.getByRole("heading", { name: "Versionshinweise" })).toBeVisible();
  await expect(page.getByLabel("Sprache")).toHaveValue("de");
  await expect(page.getByRole("button", { name: "Updates abonnieren" })).toBeVisible();
  await expect(page.getByText("Veröffentlicht: 5. Oktober 2026")).toBeVisible();
  await expect(html(page)).toHaveAttribute("lang", "de");
});

test("english switches everything back", async ({ page }) => {
  await page.getByLabel("Language").selectOption("de");
  await expect(html(page)).toHaveAttribute("lang", "de");
  await page.getByLabel("Sprache").selectOption("en");
  await expect(page.getByRole("heading", { name: "Release notes" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Subscribe to updates" })).toBeVisible();
  await expect(page.getByText("Published: October 5, 2026")).toBeVisible();
  await expect(html(page)).toHaveAttribute("lang", "en");
});

test("the choice survives a reload", async ({ page }) => {
  await page.getByLabel("Language").selectOption("de");
  await expect(page.getByRole("heading", { name: "Versionshinweise" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Versionshinweise" })).toBeVisible();
  await expect(html(page)).toHaveAttribute("lang", "de");
  await expect(page.getByLabel("Sprache")).toHaveValue("de");
});
