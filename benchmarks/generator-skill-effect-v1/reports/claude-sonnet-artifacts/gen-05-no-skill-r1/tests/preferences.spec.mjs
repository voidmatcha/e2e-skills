import { expect, test } from "@playwright/test";

// The page fills the controls from GET /api/preferences after load, so wait
// for that response (and the resulting render) before interacting.
async function open(page) {
  const loaded = page.waitForResponse(
    (r) => r.url().endsWith("/api/preferences") && r.request().method() === "GET",
  );
  await page.goto("/");
  const stored = await (await loaded).json();
  await expect(page.locator("#pf-dark")).toBeChecked({ checked: stored.theme === "dark" });
  await expect(page.locator("#pf-language")).toHaveValue(stored.language);
}

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await open(page);
});

test("dark mode toggles the page theme immediately", async ({ page }) => {
  const html = page.locator("html");
  await expect(html).toHaveAttribute("data-theme", "light");
  await page.getByLabel("Dark mode").check();
  await expect(html).toHaveAttribute("data-theme", "dark");
  await page.getByLabel("Dark mode").uncheck();
  await expect(html).toHaveAttribute("data-theme", "light");
});

test("save shows the confirmation status", async ({ page }) => {
  await page.getByLabel("Dark mode").check();
  await page.getByLabel("Language").selectOption("de");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Preferences saved");
});

test("saved choices survive a reload", async ({ page }) => {
  await page.getByLabel("Dark mode").check();
  await page.getByLabel("Language").selectOption("fr");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Preferences saved");

  await open(page);
  await expect(page.getByLabel("Dark mode")).toBeChecked();
  await expect(page.getByLabel("Language")).toHaveValue("fr");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("unsaved changes are lost on reload", async ({ page }) => {
  await page.getByLabel("Dark mode").check();
  await page.getByLabel("Language").selectOption("de");

  await open(page);
  await expect(page.getByLabel("Dark mode")).not.toBeChecked();
  await expect(page.getByLabel("Language")).toHaveValue("en");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("unsaved changes after a save revert to the saved values", async ({ page }) => {
  await page.getByLabel("Language").selectOption("de");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Preferences saved");
  await page.getByLabel("Dark mode").check();

  await open(page);
  await expect(page.getByLabel("Dark mode")).not.toBeChecked();
  await expect(page.getByLabel("Language")).toHaveValue("de");
});

test("changing dark mode clears the status", async ({ page }) => {
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Preferences saved");
  await page.getByLabel("Dark mode").check();
  await expect(page.getByRole("status")).toHaveText("");
});

test("changing language clears the status", async ({ page }) => {
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Preferences saved");
  await page.getByLabel("Language").selectOption("fr");
  await expect(page.getByRole("status")).toHaveText("");
});
