import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("saves profile changes, resets edits, and restores saved values after reload", async ({ page }) => {
  await page.goto("/");

  const displayName = page.getByLabel("Display name");
  const bio = page.getByLabel("Bio");
  const save = page.getByRole("button", { name: "Save" });

  await expect(displayName).toHaveValue("Ada");
  await expect(bio).toHaveValue("");
  await expect(save).toBeDisabled();

  await displayName.fill("Ada Lovelace");
  await bio.fill("First programmer");
  await expect(save).toBeEnabled();

  await page.getByRole("button", { name: "Reset" }).click();
  await expect(displayName).toHaveValue("Ada");
  await expect(bio).toHaveValue("");
  await expect(save).toBeDisabled();

  await displayName.fill("Ada Lovelace");
  await bio.fill("First programmer");
  await save.click();

  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(save).toBeDisabled();

  await page.reload();
  await expect(displayName).toHaveValue("Ada Lovelace");
  await expect(bio).toHaveValue("First programmer");
  await expect(save).toBeDisabled();
});

test("saving notifications keeps saved profile values", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Display name").fill("Grace Hopper");
  await page.getByLabel("Bio").fill("Compiler pioneer");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.getByRole("tab", { name: "Notifications" }).click();
  await expect(page.getByRole("tab", { name: "Notifications" })).toHaveAttribute("aria-selected", "true");

  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("daily");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace Hopper");
  await expect(page.getByLabel("Bio")).toHaveValue("Compiler pioneer");

  await page.getByRole("tab", { name: "Notifications" }).click();
  await expect(page.getByLabel("Email alerts")).toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("daily");
});

test("guards tab switches with unsaved changes and can keep or discard edits", async ({ page }) => {
  await page.goto("/");

  const profileTab = page.getByRole("tab", { name: "Profile" });
  const notificationsTab = page.getByRole("tab", { name: "Notifications" });
  const displayName = page.getByLabel("Display name");
  const save = page.getByRole("button", { name: "Save" });
  const guard = page.getByRole("alertdialog", { name: "Unsaved changes" });

  await expect(displayName).toHaveValue("Ada");

  await displayName.fill("Temporary Ada");
  await notificationsTab.click();

  await expect(guard).toBeVisible();
  await expect(page.getByText("You have unsaved changes")).toBeVisible();
  await expect(profileTab).toHaveAttribute("aria-selected", "true");
  await expect(displayName).toHaveValue("Temporary Ada");

  await page.getByRole("button", { name: "Keep editing" }).click();
  await expect(guard).toBeHidden();
  await expect(profileTab).toHaveAttribute("aria-selected", "true");
  await expect(displayName).toHaveValue("Temporary Ada");
  await expect(save).toBeEnabled();

  await notificationsTab.click();
  await expect(guard).toBeVisible();
  await page.getByRole("button", { name: "Discard" }).click();

  await expect(guard).toBeHidden();
  await expect(notificationsTab).toHaveAttribute("aria-selected", "true");
  await expect(save).toBeDisabled();

  await profileTab.click();
  await expect(displayName).toHaveValue("Ada");
});
