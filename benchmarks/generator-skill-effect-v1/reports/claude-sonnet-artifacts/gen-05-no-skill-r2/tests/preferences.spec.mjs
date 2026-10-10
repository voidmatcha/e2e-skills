import { expect, test } from "@playwright/test";

// Loads the page and waits until the stored preferences have been applied,
// so interactions cannot race the initial fetch.
async function open(page) {
  const loaded = page.waitForResponse((r) => r.url().endsWith("/api/preferences") && r.request().method() === "GET");
  await page.goto("/");
  await loaded;
  await expect(page.getByRole("heading", { name: "Preferences" })).toBeVisible();
}

test.beforeEach(async ({ request, page }) => {
  await request.post("/api/reset");
  await open(page);
});

test("ticking Dark mode switches the theme immediately", async ({ page }) => {
  const html = page.locator("html");
  await expect(html).toHaveAttribute("data-theme", "light");
  await page.getByLabel("Dark mode").check();
  await expect(html).toHaveAttribute("data-theme", "dark");
  await page.getByLabel("Dark mode").uncheck();
  await expect(html).toHaveAttribute("data-theme", "light");
});

test("Save shows the status message", async ({ page }) => {
  await page.getByLabel("Dark mode").check();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Preferences saved");
});

test("saved values persist across a reload", async ({ page }) => {
  await page.getByLabel("Dark mode").check();
  await page.getByLabel("Language").selectOption("de");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Preferences saved");

  await open(page);
  await expect(page.getByLabel("Dark mode")).toBeChecked();
  await expect(page.getByLabel("Language")).toHaveValue("de");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("unsaved changes are lost on reload", async ({ page }) => {
  await page.getByLabel("Dark mode").check();
  await page.getByLabel("Language").selectOption("fr");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Preferences saved");

  await page.getByLabel("Dark mode").uncheck();
  await page.getByLabel("Language").selectOption("de");
  await open(page);
  await expect(page.getByLabel("Dark mode")).toBeChecked();
  await expect(page.getByLabel("Language")).toHaveValue("fr");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("unsaved changes from defaults are lost on reload", async ({ page }) => {
  await page.getByLabel("Dark mode").check();
  await page.getByLabel("Language").selectOption("de");
  await open(page);
  await expect(page.getByLabel("Dark mode")).not.toBeChecked();
  await expect(page.getByLabel("Language")).toHaveValue("en");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

for (const [name, change] of [
  ["Dark mode", (page) => page.getByLabel("Dark mode").check()],
  ["Language", (page) => page.getByLabel("Language").selectOption("de")],
]) {
  test(`changing ${name} clears the status message`, async ({ page }) => {
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status")).toHaveText("Preferences saved");
    await change(page);
    await expect(page.getByRole("status")).toBeEmpty();
  });
}
