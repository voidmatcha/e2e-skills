import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
});

const save = (page) => page.getByRole("button", { name: "Save" });
const profileTab = (page) => page.getByRole("tab", { name: "Profile" });
const notificationsTab = (page) => page.getByRole("tab", { name: "Notifications" });

test("save is disabled until a field changes", async ({ page }) => {
  await expect(save(page)).toBeDisabled();
  await page.getByLabel("Bio").fill("Hello");
  await expect(save(page)).toBeEnabled();
});

test("save is disabled again after saving, with a status", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(save(page)).toBeDisabled();
});

test("reverting an edit by hand disables save again", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await expect(save(page)).toBeEnabled();
  await page.getByLabel("Display name").fill("Ada");
  await expect(save(page)).toBeDisabled();
});

test("reset restores saved values on both tabs", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await page.getByLabel("Bio").fill("Pioneer");
  await save(page).click();
  await expect(save(page)).toBeDisabled();

  await page.getByLabel("Display name").fill("Edited");
  await page.getByLabel("Bio").fill("Edited bio");
  await page.getByRole("button", { name: "Reset" }).click();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await expect(page.getByLabel("Bio")).toHaveValue("Pioneer");
  await expect(save(page)).toBeDisabled();

  // Notifications edits are reset too (reset is reachable without switching tabs via the shared actions).
  await notificationsTab(page).click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("daily");
  await page.getByRole("button", { name: "Reset" }).click();
  await expect(page.getByLabel("Email alerts")).not.toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("weekly");
  await expect(save(page)).toBeDisabled();
});

test("reload shows what was last saved", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await page.getByLabel("Bio").fill("Pioneer");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.getByLabel("Bio").fill("Unsaved");
  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await expect(page.getByLabel("Bio")).toHaveValue("Pioneer");
  await expect(save(page)).toBeDisabled();
});

test("saving on one tab keeps the other tab's saved values", async ({ page }) => {
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

  // And the other direction: save a profile change, notifications stay.
  await profileTab(page).click();
  await page.getByLabel("Bio").fill("Pioneer");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await page.reload();
  await notificationsTab(page).click();
  await expect(page.getByLabel("Email alerts")).toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("daily");
});

test("switching tabs without changes does not prompt", async ({ page }) => {
  await notificationsTab(page).click();
  await expect(notificationsTab(page)).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("You have unsaved changes")).toBeHidden();
});

test("keep editing stays on the tab with edits intact", async ({ page }) => {
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
  await page.getByRole("button", { name: "Discard" }).click();

  await expect(page.getByText("You have unsaved changes")).toBeHidden();
  await expect(notificationsTab(page)).toHaveAttribute("aria-selected", "true");
  await expect(save(page)).toBeDisabled();

  await profileTab(page).click();
  await expect(page.getByText("You have unsaved changes")).toBeHidden();
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
});

test("discard drops edits made on the notifications tab", async ({ page }) => {
  await notificationsTab(page).click();
  await page.getByLabel("Email alerts").check();
  await profileTab(page).click();
  await page.getByRole("button", { name: "Discard" }).click();

  await expect(profileTab(page)).toHaveAttribute("aria-selected", "true");
  await notificationsTab(page).click();
  await expect(page.getByLabel("Email alerts")).not.toBeChecked();
});
