import { expect, test } from "@playwright/test";

// The page fills its controls from GET /api/preferences after load, which
// overwrites anything touched earlier, so every navigation waits for that read.
const isPreferencesRead = (response) =>
  new URL(response.url()).pathname === "/api/preferences" && response.request().method() === "GET";

const open = async (page) => {
  const loaded = page.waitForResponse(isPreferencesRead);
  await page.goto("/");
  await loaded;
};

const reopen = async (page) => {
  const loaded = page.waitForResponse(isPreferencesRead);
  await page.reload();
  await loaded;
};

test.beforeEach(async ({ page, request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBe(true);
  await open(page);
});

test("ticking Dark mode switches the page theme immediately", async ({ page }) => {
  const darkMode = page.getByLabel("Dark mode");
  const html = page.locator("html");

  await expect(html).toHaveAttribute("data-theme", "light");

  await darkMode.check();
  await expect(html).toHaveAttribute("data-theme", "dark");

  await darkMode.uncheck();
  await expect(html).toHaveAttribute("data-theme", "light");
});

test("Save stores the current choices and shows the saved status", async ({ page }) => {
  await page.getByLabel("Dark mode").check();
  await page.getByLabel("Language").selectOption("de");

  const save = page.waitForRequest((r) => r.method() === "PUT" && new URL(r.url()).pathname === "/api/preferences");
  await page.getByRole("button", { name: "Save" }).click();
  expect((await save).postDataJSON()).toEqual({ theme: "dark", language: "de" });

  await expect(page.getByRole("status")).toHaveText("Preferences saved");
});

test("saved choices are shown again after a reload", async ({ page }) => {
  await page.getByLabel("Dark mode").check();
  await page.getByLabel("Language").selectOption("fr");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Preferences saved");

  await reopen(page);

  await expect(page.getByLabel("Dark mode")).toBeChecked();
  await expect(page.getByLabel("Language")).toHaveValue("fr");
});

test("changes that were not saved are lost on reload", async ({ page }) => {
  await page.getByLabel("Language").selectOption("de");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Preferences saved");

  await page.getByLabel("Dark mode").check();
  await page.getByLabel("Language").selectOption("fr");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await reopen(page);

  await expect(page.getByLabel("Dark mode")).not.toBeChecked();
  await expect(page.getByLabel("Language")).toHaveValue("de");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("changing Dark mode clears the saved status", async ({ page }) => {
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Preferences saved");

  await page.getByLabel("Dark mode").check();

  await expect(page.getByRole("status")).toBeEmpty();
});

test("changing Language clears the saved status", async ({ page }) => {
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Preferences saved");

  await page.getByLabel("Language").selectOption("de");

  await expect(page.getByRole("status")).toBeEmpty();
});
