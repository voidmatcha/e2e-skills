import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
});

const profileTab = (page) => page.getByRole("tab", { name: "Profile" });
const notificationsTab = (page) => page.getByRole("tab", { name: "Notifications" });
const save = (page) => page.getByRole("button", { name: "Save" });
const reset = (page) => page.getByRole("button", { name: "Reset" });

test("shows the saved defaults", async ({ page }) => {
  await expect(page.getByLabel("Bio")).toHaveValue("");
  await expect(save(page)).toBeDisabled();
  await notificationsTab(page).click();
  await expect(page.getByLabel("Email alerts")).not.toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("weekly");
});

test("save is enabled by an edit, disabled again after saving, with a status", async ({ page }) => {
  await expect(save(page)).toBeDisabled();
  await page.getByLabel("Display name").fill("Grace");
  await expect(save(page)).toBeEnabled();
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(save(page)).toBeDisabled();
});

test("save becomes disabled again when an edit is reverted by hand", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await expect(save(page)).toBeEnabled();
  await page.getByLabel("Display name").fill("Ada");
  await expect(save(page)).toBeDisabled();
});

test("reset restores every field to the saved values", async ({ page }) => {
  await notificationsTab(page).click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("daily");
  await reset(page).click();
  await expect(page.getByLabel("Email alerts")).not.toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("weekly");
  await expect(save(page)).toBeDisabled();
});

test("reset on the profile tab restores profile fields to the last saved values", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await page.getByLabel("Bio").fill("Pioneer");
  await save(page).click();
  await expect(save(page)).toBeDisabled();
  await page.getByLabel("Display name").fill("Other");
  await page.getByLabel("Bio").fill("Changed");
  await reset(page).click();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await expect(page.getByLabel("Bio")).toHaveValue("Pioneer");
  await expect(save(page)).toBeDisabled();
});

test("reload shows what was last saved, not unsaved edits", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await page.getByLabel("Display name").fill("Unsaved");
  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await expect(save(page)).toBeDisabled();
});

test("saving from one tab keeps the other tab's saved values", async ({ page }) => {
  await notificationsTab(page).click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("daily");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await profileTab(page).click();
  await page.getByLabel("Display name").fill("Grace");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await notificationsTab(page).click();
  await expect(page.getByLabel("Email alerts")).toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("daily");
});

test("saving notifications keeps the saved profile values", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await page.getByLabel("Bio").fill("Pioneer");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await notificationsTab(page).click();
  await page.getByLabel("Digest").selectOption("never");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await expect(page.getByLabel("Bio")).toHaveValue("Pioneer");
  await notificationsTab(page).click();
  await expect(page.getByLabel("Digest")).toHaveValue("never");
});

test("switching tabs without changes does not prompt", async ({ page }) => {
  await notificationsTab(page).click();
  await expect(notificationsTab(page)).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("You have unsaved changes")).toBeHidden();
});

test("keep editing stays on the current tab with edits intact", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await notificationsTab(page).click();
  await expect(page.getByText("You have unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Keep editing" }).click();
  await expect(page.getByText("You have unsaved changes")).toBeHidden();
  await expect(profileTab(page)).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await expect(save(page)).toBeEnabled();
});

test("discard switches tabs and drops the edits", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await notificationsTab(page).click();
  await expect(page.getByText("You have unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Discard" }).click();
  await expect(page.getByText("You have unsaved changes")).toBeHidden();
  await expect(notificationsTab(page)).toHaveAttribute("aria-selected", "true");
  await expect(save(page)).toBeDisabled();
  await profileTab(page).click();
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
});

test("unsaved notification edits also prompt when leaving that tab", async ({ page }) => {
  await notificationsTab(page).click();
  await page.getByLabel("Email alerts").check();
  await profileTab(page).click();
  await expect(page.getByText("You have unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Discard" }).click();
  await expect(profileTab(page)).toHaveAttribute("aria-selected", "true");
  await notificationsTab(page).click();
  await expect(page.getByLabel("Email alerts")).not.toBeChecked();
});
