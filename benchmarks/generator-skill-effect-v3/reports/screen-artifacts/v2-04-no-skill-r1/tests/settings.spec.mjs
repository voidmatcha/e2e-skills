import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
});

const save = (page) => page.getByRole("button", { name: "Save" });
const reset = (page) => page.getByRole("button", { name: "Reset" });
const profileTab = (page) => page.getByRole("tab", { name: "Profile" });
const notificationsTab = (page) => page.getByRole("tab", { name: "Notifications" });

test("loads the defaults with Save disabled", async ({ page }) => {
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
  await expect(page.getByLabel("Bio")).toHaveValue("");
  await expect(save(page)).toBeDisabled();
  await notificationsTab(page).click();
  await expect(page.getByLabel("Email alerts")).not.toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("weekly");
});

test("Save enables on change, saves, and disables again", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await expect(save(page)).toBeEnabled();
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(save(page)).toBeDisabled();
});

test("Save disables again when the edit is reverted by hand", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await expect(save(page)).toBeEnabled();
  await page.getByLabel("Display name").fill("Ada");
  await expect(save(page)).toBeDisabled();
});

test("a reload shows what was saved", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await page.getByLabel("Bio").fill("Compiler pioneer");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await expect(page.getByLabel("Bio")).toHaveValue("Compiler pioneer");
});

test("a reload drops unsaved edits", async ({ page }) => {
  await page.getByLabel("Display name").fill("Unsaved");
  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
  await expect(save(page)).toBeDisabled();
});

test("Reset restores the profile fields to the saved values", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await page.getByLabel("Bio").fill("Hello");
  await save(page).click();
  await expect(save(page)).toBeDisabled();

  await page.getByLabel("Display name").fill("Other");
  await page.getByLabel("Bio").fill("Changed");
  await reset(page).click();

  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await expect(page.getByLabel("Bio")).toHaveValue("Hello");
  await expect(save(page)).toBeDisabled();
});

test("Reset restores notification fields", async ({ page }) => {
  await notificationsTab(page).click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("never");
  await expect(save(page)).toBeEnabled();
  await reset(page).click();
  await expect(page.getByLabel("Email alerts")).not.toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("weekly");
  await expect(save(page)).toBeDisabled();
});

test("saving from one tab keeps the other tab's saved values", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await notificationsTab(page).click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("daily");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await notificationsTab(page).click();
  await expect(page.getByLabel("Email alerts")).toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("daily");

  await profileTab(page).click();
  await page.getByLabel("Bio").fill("Hi");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await page.reload();
  await notificationsTab(page).click();
  await expect(page.getByLabel("Email alerts")).toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("daily");
});

test("switching tabs without changes shows no prompt", async ({ page }) => {
  await notificationsTab(page).click();
  await expect(notificationsTab(page)).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("You have unsaved changes")).toBeHidden();
});

test("Keep editing stays on the tab with edits intact", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await notificationsTab(page).click();
  await expect(page.getByText("You have unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Keep editing" }).click();

  await expect(page.getByText("You have unsaved changes")).toBeHidden();
  await expect(profileTab(page)).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await expect(save(page)).toBeEnabled();
});

test("Discard switches tabs and drops the edits", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await notificationsTab(page).click();
  await page.getByRole("button", { name: "Discard" }).click();

  await expect(page.getByText("You have unsaved changes")).toBeHidden();
  await expect(notificationsTab(page)).toHaveAttribute("aria-selected", "true");
  await expect(save(page)).toBeDisabled();
  await profileTab(page).click();
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
});

test("unsaved changes in the Notifications tab also guard switching", async ({ page }) => {
  await notificationsTab(page).click();
  await page.getByLabel("Email alerts").check();
  await profileTab(page).click();
  await expect(page.getByText("You have unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Keep editing" }).click();
  await expect(page.getByLabel("Email alerts")).toBeChecked();
  await expect(notificationsTab(page)).toHaveAttribute("aria-selected", "true");
});
