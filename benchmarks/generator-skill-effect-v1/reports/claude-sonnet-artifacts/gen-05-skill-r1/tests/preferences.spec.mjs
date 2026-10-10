import { expect, test } from "@playwright/test";

// /api/reset is the app's test seam; the server is started (and discarded) by the Playwright config.
test.beforeEach(async ({ request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBe(true);
});

// The page fills its controls from GET /api/preferences after load; wait for that
// response so a later interaction is not overwritten by the stored values.
async function openPreferences(page) {
  const loaded = page.waitForResponse(
    (r) => r.url().endsWith("/api/preferences") && r.request().method() === "GET",
  );
  await page.goto("/");
  const response = await loaded;
  await response.finished();

  return {
    html: page.locator("html"),
    darkMode: page.getByRole("checkbox", { name: "Dark mode" }),
    language: page.getByLabel("Language"),
    save: page.getByRole("button", { name: "Save" }),
    status: page.getByRole("status"),
  };
}

async function reloadPreferences(page) {
  const loaded = page.waitForResponse(
    (r) => r.url().endsWith("/api/preferences") && r.request().method() === "GET",
  );
  await page.reload();
  await (await loaded).finished();
}

test("ticking Dark mode switches the theme to dark", async ({ page }) => {
  const prefs = await openPreferences(page);
  await expect(prefs.html).toHaveAttribute("data-theme", "light");

  await prefs.darkMode.check();

  await expect(prefs.html).toHaveAttribute("data-theme", "dark");
});

test("unticking Dark mode switches the theme back to light", async ({ page }) => {
  const prefs = await openPreferences(page);
  await prefs.darkMode.check();
  await expect(prefs.html).toHaveAttribute("data-theme", "dark");

  await prefs.darkMode.uncheck();

  await expect(prefs.html).toHaveAttribute("data-theme", "light");
});

test("Save stores the choices and shows Preferences saved", async ({ page }) => {
  const prefs = await openPreferences(page);
  await prefs.darkMode.check();
  await prefs.language.selectOption("de");

  const put = page.waitForRequest((r) => r.url().endsWith("/api/preferences") && r.method() === "PUT");
  await prefs.save.click();
  const request = await put;

  await expect(prefs.status).toHaveText("Preferences saved");
  expect(request.postDataJSON()).toEqual({ theme: "dark", language: "de" });
});

test("saved choices are shown again after a reload", async ({ page }) => {
  const prefs = await openPreferences(page);
  await prefs.darkMode.check();
  await prefs.language.selectOption("fr");
  await prefs.save.click();
  await expect(prefs.status).toHaveText("Preferences saved");

  await reloadPreferences(page);

  await expect(prefs.darkMode).toBeChecked();
  await expect(prefs.language).toHaveValue("fr");
  await expect(prefs.html).toHaveAttribute("data-theme", "dark");
});

test("a change that was not saved is lost on reload", async ({ page, request }) => {
  const stored = await request.put("/api/preferences", { data: { theme: "dark", language: "de" } });
  expect(stored.ok()).toBe(true);
  const prefs = await openPreferences(page);
  await expect(prefs.darkMode).toBeChecked();
  await expect(prefs.language).toHaveValue("de");

  await prefs.darkMode.uncheck();
  await prefs.language.selectOption("fr");
  await expect(prefs.html).toHaveAttribute("data-theme", "light");
  await reloadPreferences(page);

  await expect(prefs.darkMode).toBeChecked();
  await expect(prefs.language).toHaveValue("de");
  await expect(prefs.html).toHaveAttribute("data-theme", "dark");
});

test("changing Dark mode clears the status message", async ({ page }) => {
  const prefs = await openPreferences(page);
  await prefs.save.click();
  await expect(prefs.status).toHaveText("Preferences saved");

  await prefs.darkMode.check();

  await expect(prefs.status).toHaveText("");
});

test("changing the Language clears the status message", async ({ page }) => {
  const prefs = await openPreferences(page);
  await prefs.save.click();
  await expect(prefs.status).toHaveText("Preferences saved");

  await prefs.language.selectOption("de");

  await expect(prefs.status).toHaveText("");
});
