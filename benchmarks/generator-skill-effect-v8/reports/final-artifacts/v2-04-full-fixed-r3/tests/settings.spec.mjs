import { expect, test } from "@playwright/test";

const openSettings = async (page) => {
  await page.goto("/");
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
};

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("starts with saved profile values and disabled save", async ({ page }) => {
  await openSettings(page);

  await expect(page.getByRole("tab", { name: "Profile", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
  await expect(page.getByLabel("Bio")).toHaveValue("");
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
});

test("saves profile changes and restores them after reload", async ({ page }) => {
  await openSettings(page);

  await page.getByLabel("Display name").fill("Ada Lovelace");
  await page.getByLabel("Bio").fill("First programmer");
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeEnabled();

  const saveRequest = page.waitForRequest((request) => {
    if (request.method() !== "PUT" || !request.url().endsWith("/api/settings")) return false;
    const body = request.postDataJSON();
    return body.displayName === "Ada Lovelace" && body.bio === "First programmer";
  });
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await saveRequest;

  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();

  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Ada Lovelace");
  await expect(page.getByLabel("Bio")).toHaveValue("First programmer");
});

test("saves notifications without losing saved profile values", async ({ page }) => {
  await openSettings(page);

  await page.getByLabel("Display name").fill("Grace Hopper");
  await page.getByLabel("Bio").fill("Compiler pioneer");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.getByRole("tab", { name: "Notifications", exact: true }).click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("daily");

  const saveRequest = page.waitForRequest((request) => {
    if (request.method() !== "PUT" || !request.url().endsWith("/api/settings")) return false;
    const body = request.postDataJSON();
    return body.displayName === "Grace Hopper" && body.bio === "Compiler pioneer" && body.emailAlerts === true && body.digest === "daily";
  });
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await saveRequest;

  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();

  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace Hopper");
  await expect(page.getByLabel("Bio")).toHaveValue("Compiler pioneer");
  await page.getByRole("tab", { name: "Notifications", exact: true }).click();
  await expect(page.getByLabel("Email alerts")).toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("daily");
});

test("saves profile without losing saved notification values", async ({ page }) => {
  await openSettings(page);

  await page.getByRole("tab", { name: "Notifications", exact: true }).click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("never");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.getByRole("tab", { name: "Profile", exact: true }).click();
  await page.getByLabel("Display name").fill("Margaret Hamilton");
  await page.getByLabel("Bio").fill("Apollo software lead");

  const saveRequest = page.waitForRequest((request) => {
    if (request.method() !== "PUT" || !request.url().endsWith("/api/settings")) return false;
    const body = request.postDataJSON();
    return body.displayName === "Margaret Hamilton" && body.bio === "Apollo software lead" && body.emailAlerts === true && body.digest === "never";
  });
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await saveRequest;

  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.reload();
  await page.getByRole("tab", { name: "Notifications", exact: true }).click();
  await expect(page.getByLabel("Email alerts")).toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("never");
});

test("resets fields to the saved values", async ({ page }) => {
  await openSettings(page);

  await page.getByLabel("Display name").fill("Katherine Johnson");
  await page.getByLabel("Bio").fill("Orbital calculations");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.getByRole("tab", { name: "Notifications", exact: true }).click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("never");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.getByRole("tab", { name: "Profile", exact: true }).click();
  await page.getByLabel("Display name").fill("Unsaved name");
  await page.getByLabel("Bio").fill("Unsaved bio");
  await page.getByRole("button", { name: "Reset", exact: true }).click();

  await expect(page.getByLabel("Display name")).toHaveValue("Katherine Johnson");
  await expect(page.getByLabel("Bio")).toHaveValue("Orbital calculations");
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();

  await page.getByRole("tab", { name: "Notifications", exact: true }).click();
  await page.getByLabel("Email alerts").uncheck();
  await page.getByLabel("Digest").selectOption("daily");
  await page.getByRole("button", { name: "Reset", exact: true }).click();

  await expect(page.getByLabel("Email alerts")).toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("never");
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
});

test("keeps profile edits when staying on the current tab", async ({ page }) => {
  await openSettings(page);

  await page.getByLabel("Display name").fill("Unsaved Ada");
  await page.getByRole("tab", { name: "Notifications", exact: true }).click();

  const dialog = page.getByRole("alertdialog", { name: "Unsaved changes", exact: true });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("You have unsaved changes", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Keep editing", exact: true }).click();

  await expect(page.getByRole("tab", { name: "Profile", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Display name")).toHaveValue("Unsaved Ada");
});

test("discards profile edits when switching tabs", async ({ page }) => {
  await openSettings(page);

  await page.getByLabel("Display name").fill("Temporary Ada");
  await page.getByRole("tab", { name: "Notifications", exact: true }).click();
  const dialog = page.getByRole("alertdialog", { name: "Unsaved changes", exact: true });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("You have unsaved changes", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Discard", exact: true }).click();

  await expect(page.getByRole("tab", { name: "Notifications", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Email alerts")).not.toBeChecked();

  await page.getByRole("tab", { name: "Profile", exact: true }).click();
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
});
