import { expect, test } from "@playwright/test";

const dark = (page) => page.getByLabel("Dark mode");
const language = (page) => page.getByLabel("Language");
const html = (page) => page.locator("html");

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(dark(page)).not.toBeChecked();
});

test("dark mode switches the theme immediately", async ({ page }) => {
  await expect(html(page)).toHaveAttribute("data-theme", "light");
  await dark(page).check();
  await expect(html(page)).toHaveAttribute("data-theme", "dark");
  await dark(page).uncheck();
  await expect(html(page)).toHaveAttribute("data-theme", "light");
});

test("save shows the status and persists both choices", async ({ page }) => {
  await dark(page).check();
  await language(page).selectOption("de");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Preferences saved");
  await page.reload();
  await expect(dark(page)).toBeChecked();
  await expect(language(page)).toHaveValue("de");
  await expect(html(page)).toHaveAttribute("data-theme", "dark");
});

test("an unsaved change is lost on reload", async ({ page }) => {
  await dark(page).check();
  await language(page).selectOption("fr");
  await expect(html(page)).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(dark(page)).not.toBeChecked();
  await expect(language(page)).toHaveValue("en");
});

test("the status clears when a control changes", async ({ page }) => {
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Preferences saved");
  await language(page).selectOption("fr");
  await expect(page.getByRole("status")).toHaveText("");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Preferences saved");
  await dark(page).check();
  await expect(page.getByRole("status")).toHaveText("");
});
