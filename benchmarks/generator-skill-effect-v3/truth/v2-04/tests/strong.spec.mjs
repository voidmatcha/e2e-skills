import { expect, test } from "@playwright/test";

const save = (page) => page.getByRole("button", { name: "Save" });
const tab = (page, name) => page.getByRole("tab", { name });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
});

test("save is disabled until dirty and again after saving", async ({ page }) => {
  await expect(save(page)).toBeDisabled();
  await page.getByLabel("Bio").fill("Mathematician");
  await expect(save(page)).toBeEnabled();
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(save(page)).toBeDisabled();
  await page.reload();
  await expect(page.getByLabel("Bio")).toHaveValue("Mathematician");
});

test("reset restores every field", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await tab(page, "Notifications").click();
  await page.getByRole("button", { name: "Discard" }).click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("never");
  await tab(page, "Profile").click();
  await page.getByRole("button", { name: "Discard" }).click();
  await page.getByLabel("Display name").fill("Grace");
  await tab(page, "Notifications").click();
  await page.getByRole("button", { name: "Keep editing" }).click();
  await page.getByRole("button", { name: "Reset" }).click();
  await expect(page.getByLabel("Display name")).toHaveValue("Ada");
  await tab(page, "Notifications").click();
  await expect(page.getByLabel("Email alerts")).not.toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("weekly");
});

test("reset after editing both tabs restores the notifications fields too", async ({ page }) => {
  await tab(page, "Notifications").click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("daily");
  await page.getByRole("button", { name: "Reset" }).click();
  await expect(page.getByLabel("Email alerts")).not.toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("weekly");
  await expect(save(page)).toBeDisabled();
});

test("saving from one tab keeps the other tab's saved values", async ({ page }) => {
  await tab(page, "Notifications").click();
  await page.getByLabel("Email alerts").check();
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await tab(page, "Profile").click();
  await page.getByLabel("Display name").fill("Grace");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await tab(page, "Notifications").click();
  await expect(page.getByLabel("Email alerts")).toBeChecked();
});

test("switching tabs with unsaved changes asks first", async ({ page }) => {
  await page.getByLabel("Bio").fill("Unsaved");
  await tab(page, "Notifications").click();
  await expect(page.getByRole("alertdialog", { name: "Unsaved changes" })).toBeVisible();
  await expect(page.getByText("You have unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Keep editing" }).click();
  await expect(tab(page, "Profile")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Bio")).toHaveValue("Unsaved");
  await tab(page, "Notifications").click();
  await page.getByRole("button", { name: "Discard" }).click();
  await expect(tab(page, "Notifications")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Digest")).toBeVisible();
  await tab(page, "Profile").click();
  await expect(page.getByLabel("Bio")).toHaveValue("");
});
