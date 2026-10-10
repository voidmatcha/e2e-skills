import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("saves profile changes, disables save again, and restores them after reload", async ({ page }) => {
  await page.goto("/");

  const save = page.getByRole("button", { name: "Save" });
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
  await expect(page.getByLabel("Bio")).toHaveValue("");
  await expect(save).toBeDisabled();

  await page.getByLabel("Display name").fill("Grace");
  await page.getByLabel("Bio").fill("Compiler pioneer");
  await expect(save).toBeEnabled();

  await save.click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(save).toBeDisabled();

  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await expect(page.getByLabel("Bio")).toHaveValue("Compiler pioneer");
  await expect(save).toBeDisabled();
});

test("resets profile fields to the last saved values", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Display name").fill("Katherine");
  await page.getByLabel("Bio").fill("Orbital mechanics");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();

  await page.getByLabel("Display name").fill("Unsaved name");
  await page.getByLabel("Bio").fill("Unsaved bio");
  await expect(page.getByRole("button", { name: "Save" })).toBeEnabled();

  await page.getByRole("button", { name: "Reset" }).click();
  await expect(page.getByLabel("Display name")).toHaveValue("Katherine");
  await expect(page.getByLabel("Bio")).toHaveValue("Orbital mechanics");
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
});

test("saving from one tab keeps values saved from the other tab", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Display name").fill("Margaret");
  await page.getByLabel("Bio").fill("Apollo software");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();

  await page.getByRole("tab", { name: "Notifications" }).click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("daily");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();

  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Margaret");
  await expect(page.getByLabel("Bio")).toHaveValue("Apollo software");

  await page.getByRole("tab", { name: "Notifications" }).click();
  await expect(page.getByLabel("Email alerts")).toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("daily");
});

test("keeps editing when switching tabs with unsaved profile changes", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Display name").fill("Hedy");
  await page.getByRole("tab", { name: "Notifications" }).click();

  await expect(page.getByRole("alertdialog", { name: "Unsaved changes" })).toBeVisible();
  await page.getByRole("button", { name: "Keep editing" }).click();

  await expect(page.getByRole("alertdialog", { name: "Unsaved changes" })).toBeHidden();
  await expect(page.getByRole("tab", { name: "Profile" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Display name")).toHaveValue("Hedy");
  await expect(page.getByRole("button", { name: "Save" })).toBeEnabled();
});

test("discards unsaved changes when switching tabs", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Display name").fill("Unsaved");
  await page.getByLabel("Bio").fill("Draft");
  await page.getByRole("tab", { name: "Notifications" }).click();

  await expect(page.getByRole("alertdialog", { name: "Unsaved changes" })).toBeVisible();
  await page.getByRole("button", { name: "Discard" }).click();

  await expect(page.getByRole("alertdialog", { name: "Unsaved changes" })).toBeHidden();
  await expect(page.getByRole("tab", { name: "Notifications" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();

  await page.getByRole("tab", { name: "Profile" }).click();
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
  await expect(page.getByLabel("Bio")).toHaveValue("");
});
