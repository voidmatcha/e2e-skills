import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Account settings", exact: true })).toBeVisible();
});

test("saves profile changes, disables save, reloads saved values, and resets unsaved edits", async ({ page }) => {
  const displayName = page.getByLabel("Display name");
  const bio = page.getByLabel("Bio");
  const save = page.getByRole("button", { name: "Save", exact: true });

  await expect(save).toBeDisabled();

  await displayName.fill("Grace");
  await bio.fill("First programmer");
  await expect(save).toBeEnabled();

  const saveRequest = page.waitForRequest((request) => request.method() === "PUT" && new URL(request.url()).pathname === "/api/settings");
  await save.click();
  const request = await saveRequest;
  expect(request.postDataJSON()).toEqual({
    displayName: "Grace",
    bio: "First programmer",
    emailAlerts: false,
    digest: "weekly",
  });
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(save).toBeDisabled();

  await page.reload();
  await expect(displayName).toHaveValue("Grace");
  await expect(bio).toHaveValue("First programmer");
  await expect(save).toBeDisabled();

  await displayName.fill("Katherine");
  await bio.fill("Navigation tables");
  await expect(save).toBeEnabled();
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(displayName).toHaveValue("Grace");
  await expect(bio).toHaveValue("First programmer");
  await expect(save).toBeDisabled();
});

test("saves notification changes and restores their saved values on reset", async ({ page }) => {
  const notificationsTab = page.getByRole("tab", { name: "Notifications", exact: true });
  const emailAlerts = page.getByRole("checkbox", { name: "Email alerts", exact: true });
  const digest = page.getByLabel("Digest");
  const save = page.getByRole("button", { name: "Save", exact: true });

  await notificationsTab.click();
  await expect(save).toBeDisabled();

  await emailAlerts.check();
  await digest.selectOption("daily");
  await expect(save).toBeEnabled();

  const saveRequest = page.waitForRequest((request) => request.method() === "PUT" && new URL(request.url()).pathname === "/api/settings");
  await save.click();
  const request = await saveRequest;
  expect(request.postDataJSON()).toEqual({
    displayName: "Ada",
    bio: "",
    emailAlerts: true,
    digest: "daily",
  });
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(save).toBeDisabled();

  await page.reload();
  await notificationsTab.click();
  await expect(emailAlerts).toBeChecked();
  await expect(digest).toHaveValue("daily");

  await emailAlerts.uncheck();
  await digest.selectOption("never");
  await expect(save).toBeEnabled();
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(emailAlerts).toBeChecked();
  await expect(digest).toHaveValue("daily");
  await expect(save).toBeDisabled();
});

test("saving from one tab keeps the other tab's saved values", async ({ page }) => {
  const displayName = page.getByLabel("Display name");
  const bio = page.getByLabel("Bio");
  const notificationsTab = page.getByRole("tab", { name: "Notifications", exact: true });
  const profileTab = page.getByRole("tab", { name: "Profile", exact: true });
  const emailAlerts = page.getByRole("checkbox", { name: "Email alerts", exact: true });
  const digest = page.getByLabel("Digest");
  const save = page.getByRole("button", { name: "Save", exact: true });

  await displayName.fill("Hedy");
  await bio.fill("Frequency hopping");
  await save.click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await notificationsTab.click();
  await emailAlerts.check();
  await digest.selectOption("never");
  const notificationSave = page.waitForRequest((request) => request.method() === "PUT" && new URL(request.url()).pathname === "/api/settings");
  await save.click();
  const request = await notificationSave;
  expect(request.postDataJSON()).toEqual({
    displayName: "Hedy",
    bio: "Frequency hopping",
    emailAlerts: true,
    digest: "never",
  });
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.reload();
  await profileTab.click();
  await expect(displayName).toHaveValue("Hedy");
  await expect(bio).toHaveValue("Frequency hopping");
  await notificationsTab.click();
  await expect(emailAlerts).toBeChecked();
  await expect(digest).toHaveValue("never");
});

test("offers to keep editing or discard unsaved changes when switching tabs", async ({ page }) => {
  const displayName = page.getByLabel("Display name");
  const notificationsTab = page.getByRole("tab", { name: "Notifications", exact: true });
  const dialog = page.getByRole("alertdialog", { name: "Unsaved changes", exact: true });

  await displayName.fill("Unsaved Ada");
  await notificationsTab.click();
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("You have unsaved changes");

  await page.getByRole("button", { name: "Keep editing", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("tab", { name: "Profile", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(displayName).toHaveValue("Unsaved Ada");

  await notificationsTab.click();
  await page.getByRole("button", { name: "Discard", exact: true }).click();
  await expect(notificationsTab).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Profile", exact: true }).click();
  await expect(displayName).toHaveValue("Ada");
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
});
