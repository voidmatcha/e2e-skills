import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
});

const save = (page) => page.getByRole("button", { name: "Save" });
const tab = (page, name) => page.getByRole("tab", { name });

test("shows the saved defaults", async ({ page }) => {
  await expect(page.getByLabel("Bio")).toHaveValue("");
  await expect(save(page)).toBeDisabled();
  await tab(page, "Notifications").click();
  await expect(page.getByLabel("Email alerts")).not.toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("weekly");
});

test("save is enabled by a change, and disabled again after saving", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await expect(save(page)).toBeEnabled();
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(save(page)).toBeDisabled();
});

test("reverting an edit by hand disables save", async ({ page }) => {
  await page.getByLabel("Bio").fill("hello");
  await expect(save(page)).toBeEnabled();
  await page.getByLabel("Bio").fill("");
  await expect(save(page)).toBeDisabled();
});

test("reload shows what was last saved", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await page.getByLabel("Bio").fill("Admiral");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await page.getByLabel("Bio").fill("unsaved edit");
  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await expect(page.getByLabel("Bio")).toHaveValue("Admiral");
});

test("reload drops unsaved edits", async ({ page }) => {
  await page.getByLabel("Display name").fill("Nope");
  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
  await expect(save(page)).toBeDisabled();
});

test("reset restores every field on both tabs to the saved values", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await tab(page, "Notifications").click();
  await expect(page.getByText("You have unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Keep editing" }).click();
  await page.getByLabel("Bio").fill("temp");
  await page.getByRole("button", { name: "Reset" }).click();
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
  await expect(page.getByLabel("Bio")).toHaveValue("");
  await expect(save(page)).toBeDisabled();
});

test("reset restores notification fields after a save", async ({ page }) => {
  await tab(page, "Notifications").click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("daily");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await page.getByLabel("Email alerts").uncheck();
  await page.getByLabel("Digest").selectOption("never");
  await page.getByRole("button", { name: "Reset" }).click();
  await expect(page.getByLabel("Email alerts")).toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("daily");
  await expect(save(page)).toBeDisabled();
});

test("saving from one tab keeps the other tab's saved values", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await tab(page, "Notifications").click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("never");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await tab(page, "Notifications").click();
  await expect(page.getByLabel("Email alerts")).toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("never");
});

test("saving profile after notifications were saved keeps notifications", async ({ page }) => {
  await tab(page, "Notifications").click();
  await page.getByLabel("Email alerts").check();
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await tab(page, "Profile").click();
  await page.getByLabel("Bio").fill("Hi");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.reload();
  await expect(page.getByLabel("Bio")).toHaveValue("Hi");
  await tab(page, "Notifications").click();
  await expect(page.getByLabel("Email alerts")).toBeChecked();
});

test("switching tabs without changes does not prompt", async ({ page }) => {
  await tab(page, "Notifications").click();
  await expect(tab(page, "Notifications")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("You have unsaved changes")).toBeHidden();
  await expect(page.getByLabel("Digest")).toBeVisible();
});

test("keep editing stays on the tab with edits intact", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await tab(page, "Notifications").click();
  await expect(page.getByText("You have unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Keep editing" }).click();
  await expect(page.getByText("You have unsaved changes")).toBeHidden();
  await expect(tab(page, "Profile")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await expect(save(page)).toBeEnabled();
});

test("discard switches tabs and drops the edits", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await tab(page, "Notifications").click();
  await page.getByRole("button", { name: "Discard" }).click();
  await expect(page.getByText("You have unsaved changes")).toBeHidden();
  await expect(tab(page, "Notifications")).toHaveAttribute("aria-selected", "true");
  await expect(save(page)).toBeDisabled();
  await tab(page, "Profile").click();
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
});

test("discard drops edits made on the notifications tab", async ({ page }) => {
  await tab(page, "Notifications").click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("daily");
  await tab(page, "Profile").click();
  await page.getByRole("button", { name: "Discard" }).click();
  await expect(tab(page, "Profile")).toHaveAttribute("aria-selected", "true");
  await tab(page, "Notifications").click();
  await expect(page.getByLabel("Email alerts")).not.toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("weekly");
});
