import { expect, test } from "@playwright/test";

// The page fills its controls from GET /api/preferences after load, so wait for
// that response (and one more tick for show() to run) before interacting.
async function open(page) {
  const loaded = page.waitForResponse(
    (r) => r.url().endsWith("/api/preferences") && r.request().method() === "GET",
  );
  await page.goto("/");
  await loaded;
  await page.waitForFunction(() => document.readyState === "complete");
}

test.beforeEach(async ({ request, page }) => {
  await request.post("/api/reset");
  await open(page);
});

const html = (page) => page.locator("html");
const dark = (page) => page.getByLabel("Dark mode");
const language = (page) => page.getByLabel("Language");
const status = (page) => page.getByRole("status");

test("starts with the defaults", async ({ page }) => {
  await expect(dark(page)).not.toBeChecked();
  await expect(language(page)).toHaveValue("en");
  await expect(html(page)).toHaveAttribute("data-theme", "light");
});

test("dark mode switches the theme immediately", async ({ page }) => {
  await dark(page).check();
  await expect(html(page)).toHaveAttribute("data-theme", "dark");
  await dark(page).uncheck();
  await expect(html(page)).toHaveAttribute("data-theme", "light");
});

test("save shows the confirmation status", async ({ page }) => {
  await dark(page).check();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(status(page)).toHaveText("Preferences saved");
});

test("saved choices survive a reload", async ({ page }) => {
  await dark(page).check();
  await language(page).selectOption("de");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(status(page)).toHaveText("Preferences saved");

  await open(page);
  await expect(dark(page)).toBeChecked();
  await expect(language(page)).toHaveValue("de");
  await expect(html(page)).toHaveAttribute("data-theme", "dark");
});

test("unsaved changes are lost on reload", async ({ page }) => {
  await dark(page).check();
  await language(page).selectOption("fr");

  await open(page);
  await expect(dark(page)).not.toBeChecked();
  await expect(language(page)).toHaveValue("en");
  await expect(html(page)).toHaveAttribute("data-theme", "light");
});

test("unsaved changes after a save revert to the saved values", async ({ page }) => {
  await language(page).selectOption("de");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(status(page)).toHaveText("Preferences saved");
  await dark(page).check();
  await language(page).selectOption("fr");

  await open(page);
  await expect(dark(page)).not.toBeChecked();
  await expect(language(page)).toHaveValue("de");
});

test("changing dark mode clears the status", async ({ page }) => {
  await page.getByRole("button", { name: "Save" }).click();
  await expect(status(page)).toHaveText("Preferences saved");
  await dark(page).check();
  await expect(status(page)).toHaveText("");
});

test("changing language clears the status", async ({ page }) => {
  await page.getByRole("button", { name: "Save" }).click();
  await expect(status(page)).toHaveText("Preferences saved");
  await language(page).selectOption("fr");
  await expect(status(page)).toHaveText("");
});
