import { expect, test } from "@playwright/test";

const defaults = {
  displayName: "Ada",
  bio: "",
  emailAlerts: false,
  digest: "weekly",
};

async function resetSettings(page) {
  await page.request.post("/api/reset");
}

async function expectProfile(page, values) {
  await expect(page.getByLabel("Display name")).toHaveValue(values.displayName);
  await expect(page.getByLabel("Bio")).toHaveValue(values.bio);
}

async function expectNotifications(page, values) {
  await expect(page.getByLabel("Email alerts")).toBeChecked({ checked: values.emailAlerts });
  await expect(page.getByLabel("Digest")).toHaveValue(values.digest);
}

test.beforeEach(async ({ page }) => {
  await resetSettings(page);
});

test("saves profile changes and persists them after reload", async ({ page }) => {
  await page.goto("/");

  const save = page.getByRole("button", { name: "Save" });
  await expectProfile(page, defaults);
  await expect(save).toBeDisabled();

  await page.getByLabel("Display name").fill("Ada Lovelace");
  await page.getByLabel("Bio").fill("First programmer");
  await expect(save).toBeEnabled();

  await save.click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(save).toBeDisabled();

  await page.reload();
  await expectProfile(page, { ...defaults, displayName: "Ada Lovelace", bio: "First programmer" });
  await expect(save).toBeDisabled();
});

test("saves notifications without losing saved profile values", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Display name").fill("Grace Hopper");
  await page.getByLabel("Bio").fill("Compiler pioneer");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.getByRole("tab", { name: "Notifications" }).click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("daily");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();

  await page.reload();
  await page.getByRole("tab", { name: "Notifications" }).click();
  await expectNotifications(page, {
    ...defaults,
    displayName: "Grace Hopper",
    bio: "Compiler pioneer",
    emailAlerts: true,
    digest: "daily",
  });

  await page.getByRole("tab", { name: "Profile" }).click();
  await expectProfile(page, { ...defaults, displayName: "Grace Hopper", bio: "Compiler pioneer" });
});

test("reset restores the current saved values", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Display name").fill("Katherine Johnson");
  await page.getByLabel("Bio").fill("Orbital mechanics");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.getByLabel("Display name").fill("Unsaved name");
  await page.getByLabel("Bio").fill("Unsaved bio");
  await expect(page.getByRole("button", { name: "Save" })).toBeEnabled();

  await page.getByRole("button", { name: "Reset" }).click();
  await expectProfile(page, {
    ...defaults,
    displayName: "Katherine Johnson",
    bio: "Orbital mechanics",
  });
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
});

test("keeps editing when canceling a tab switch with unsaved changes", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Display name").fill("Margaret Hamilton");
  await page.getByRole("tab", { name: "Notifications" }).click();

  await expect(page.getByRole("alertdialog", { name: "Unsaved changes" })).toBeVisible();
  await page.getByRole("button", { name: "Keep editing" }).click();

  await expect(page.getByRole("tab", { name: "Profile" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Display name")).toHaveValue("Margaret Hamilton");
  await expect(page.getByRole("button", { name: "Save" })).toBeEnabled();
});

test("discards unsaved changes when confirming a tab switch", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Display name").fill("Unsaved Ada");
  await page.getByRole("tab", { name: "Notifications" }).click();

  await expect(page.getByRole("alertdialog", { name: "Unsaved changes" })).toBeVisible();
  await page.getByRole("button", { name: "Discard" }).click();

  await expect(page.getByRole("tab", { name: "Notifications" })).toHaveAttribute("aria-selected", "true");
  await expectNotifications(page, defaults);
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();

  await page.getByRole("tab", { name: "Profile" }).click();
  await expectProfile(page, defaults);
});
