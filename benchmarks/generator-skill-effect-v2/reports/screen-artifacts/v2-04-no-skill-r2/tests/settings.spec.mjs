import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
});

const save = (page) => page.getByRole("button", { name: "Save" });
const reset = (page) => page.getByRole("button", { name: "Reset" });
const tab = (page, name) => page.getByRole("tab", { name });

test("save is disabled until something changes", async ({ page }) => {
  await expect(save(page)).toBeDisabled();
  await page.getByLabel("Bio").fill("Hello");
  await expect(save(page)).toBeEnabled();
  await page.getByLabel("Bio").fill("");
  await expect(save(page)).toBeDisabled();
});

test("saving shows status and disables save again", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(save(page)).toBeDisabled();
});

test("reload shows the last saved values", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await page.getByLabel("Bio").fill("Compilers");
  await save(page).click();
  await expect(save(page)).toBeDisabled();
  await page.getByLabel("Bio").fill("unsaved edit");
  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await expect(page.getByLabel("Bio")).toHaveValue("Compilers");
});

test("reset restores every field to saved values", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await page.getByLabel("Bio").fill("Compilers");
  await save(page).click();
  await expect(save(page)).toBeDisabled();

  await page.getByLabel("Display name").fill("Other");
  await page.getByLabel("Bio").fill("Other bio");
  await reset(page).click();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await expect(page.getByLabel("Bio")).toHaveValue("Compilers");
  await expect(save(page)).toBeDisabled();

  await tab(page, "Notifications").click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("daily");
  await reset(page).click();
  await expect(page.getByLabel("Email alerts")).not.toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("weekly");
  await expect(save(page)).toBeDisabled();
});

test("saving one tab keeps the other tab's saved values", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await save(page).click();
  await expect(save(page)).toBeDisabled();
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

test("saving notifications first keeps profile values", async ({ page }) => {
  await tab(page, "Notifications").click();
  await page.getByLabel("Digest").selectOption("daily");
  await save(page).click();
  await expect(save(page)).toBeDisabled();
  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
  await tab(page, "Notifications").click();
  await expect(page.getByLabel("Digest")).toHaveValue("daily");
});

test("switching tabs without changes does not prompt", async ({ page }) => {
  await tab(page, "Notifications").click();
  await expect(tab(page, "Notifications")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("You have unsaved changes")).toBeHidden();
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
