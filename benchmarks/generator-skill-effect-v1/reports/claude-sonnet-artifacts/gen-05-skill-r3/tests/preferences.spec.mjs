import { expect, test } from "@playwright/test";

const isPreferencesRead = (response) =>
  new URL(response.url()).pathname === "/api/preferences" && response.request().method() === "GET";

// The page paints default controls and then overwrites them with the stored
// preferences once GET /api/preferences resolves; interacting before that
// would be overwritten, so wait for the stored values to have been applied.
async function gotoPreferences(page) {
  const read = page.waitForResponse(isPreferencesRead);
  await page.goto("/");
  await (await read).finished();
  // JUSTIFIED: the app exposes no ready marker; one frame lets its fetch().then(show) chain run.
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => resolve())));
}

test.beforeEach(async ({ request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBe(true);
});

test.describe("preferences", () => {
  test("ticking Dark mode switches the page to the dark theme", async ({ page }) => {
    await gotoPreferences(page);

    await page.getByLabel("Dark mode").check();

    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  });

  test("unticking Dark mode switches the page back to the light theme", async ({ page, request }) => {
    await request.put("/api/preferences", { data: { theme: "dark", language: "en" } });
    await gotoPreferences(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

    await page.getByLabel("Dark mode").uncheck();

    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  });

  test("Save stores the current choices and reports Preferences saved", async ({ page }) => {
    await gotoPreferences(page);
    await page.getByLabel("Dark mode").check();
    await page.getByLabel("Language").selectOption("de");

    const save = page.waitForRequest((r) => r.method() === "PUT" && new URL(r.url()).pathname === "/api/preferences");
    await page.getByRole("button", { name: "Save" }).click();

    expect((await save).postDataJSON()).toEqual({ theme: "dark", language: "de" });
    await expect(page.getByRole("status")).toHaveText("Preferences saved");
  });

  test("saved choices are shown after a reload", async ({ page }) => {
    await gotoPreferences(page);
    await page.getByLabel("Dark mode").check();
    await page.getByLabel("Language").selectOption("fr");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status")).toHaveText("Preferences saved");

    await page.reload();

    await expect(page.getByLabel("Dark mode")).toBeChecked();
    await expect(page.getByLabel("Language")).toHaveValue("fr");
  });

  test("a change that was not saved is lost on reload", async ({ page }) => {
    await gotoPreferences(page);
    await page.getByLabel("Dark mode").check();
    await page.getByLabel("Language").selectOption("de");

    await page.reload();

    await expect(page.getByLabel("Dark mode")).not.toBeChecked();
    await expect(page.getByLabel("Language")).toHaveValue("en");
  });

  test("changing Dark mode clears the status message", async ({ page }) => {
    await gotoPreferences(page);
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status")).toHaveText("Preferences saved");

    await page.getByLabel("Dark mode").check();

    await expect(page.getByRole("status")).toHaveText("");
  });

  test("changing Language clears the status message", async ({ page }) => {
    await gotoPreferences(page);
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status")).toHaveText("Preferences saved");

    await page.getByLabel("Language").selectOption("de");

    await expect(page.getByRole("status")).toHaveText("");
  });
});
