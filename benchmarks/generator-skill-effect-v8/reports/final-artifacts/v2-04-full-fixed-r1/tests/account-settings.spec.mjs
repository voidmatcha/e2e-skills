import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("saves profile changes and shows them after reload", async ({ page }) => {
  await page.goto("/");

  const displayName = page.getByLabel("Display name");
  const bio = page.getByLabel("Bio");
  const save = page.getByRole("button", { name: "Save", exact: true });

  await expect(save).toBeDisabled();

  await displayName.fill("Ada Lovelace");
  await bio.fill("First programmer");
  await expect(save).toBeEnabled();

  const saveRequest = page.waitForRequest((request) => {
    if (request.method() !== "PUT" || !request.url().endsWith("/api/settings")) return false;
    return request.postDataJSON().displayName === "Ada Lovelace";
  });
  await save.click();
  await saveRequest;

  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(save).toBeDisabled();

  await page.reload();
  await expect(displayName).toHaveValue("Ada Lovelace");
  await expect(bio).toHaveValue("First programmer");
  await expect(save).toBeDisabled();
});

test("saving notifications keeps saved profile values", async ({ page }) => {
  await page.goto("/");

  const displayName = page.getByLabel("Display name");
  const bio = page.getByLabel("Bio");
  const save = page.getByRole("button", { name: "Save", exact: true });

  await displayName.fill("Grace Hopper");
  await bio.fill("Compiler pioneer");
  await save.click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.getByRole("tab", { name: "Notifications", exact: true }).click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("daily");

  const saveRequest = page.waitForRequest((request) => {
    if (request.method() !== "PUT" || !request.url().endsWith("/api/settings")) return false;
    const body = request.postDataJSON();
    return body.emailAlerts === true && body.digest === "daily";
  });
  await save.click();
  await saveRequest;

  await expect(page.getByRole("status")).toHaveText("Settings saved");
  await expect(save).toBeDisabled();

  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace Hopper");
  await expect(page.getByLabel("Bio")).toHaveValue("Compiler pioneer");

  await page.getByRole("tab", { name: "Notifications", exact: true }).click();
  await expect(page.getByLabel("Email alerts")).toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("daily");
});

test("reset restores every field to the saved values", async ({ page }) => {
  await page.goto("/");

  const displayName = page.getByLabel("Display name");
  const bio = page.getByLabel("Bio");
  const save = page.getByRole("button", { name: "Save", exact: true });
  const reset = page.getByRole("button", { name: "Reset", exact: true });

  await displayName.fill("Katherine Johnson");
  await bio.fill("Orbital mechanics");
  await save.click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.getByRole("tab", { name: "Notifications", exact: true }).click();
  await page.getByLabel("Email alerts").check();
  await page.getByLabel("Digest").selectOption("never");
  await save.click();
  await expect(page.getByRole("status")).toHaveText("Settings saved");

  await page.getByLabel("Email alerts").uncheck();
  await page.getByLabel("Digest").selectOption("daily");
  await expect(save).toBeEnabled();
  await reset.click();
  await expect(page.getByLabel("Email alerts")).toBeChecked();
  await expect(page.getByLabel("Digest")).toHaveValue("never");
  await expect(save).toBeDisabled();

  await page.getByRole("tab", { name: "Profile", exact: true }).click();
  await displayName.fill("Draft name");
  await bio.fill("Draft bio");
  await expect(save).toBeEnabled();
  await reset.click();
  await expect(displayName).toHaveValue("Katherine Johnson");
  await expect(bio).toHaveValue("Orbital mechanics");
  await expect(save).toBeDisabled();
});

test("unsaved tab changes can be kept or discarded", async ({ page }) => {
  await page.goto("/");

  const displayName = page.getByLabel("Display name");
  const profileTab = page.getByRole("tab", { name: "Profile", exact: true });
  const notificationsTab = page.getByRole("tab", { name: "Notifications", exact: true });
  const dialog = page.getByRole("alertdialog", { name: "Unsaved changes", exact: true });

  await displayName.fill("Unsaved Ada");
  await notificationsTab.click();
  await expect(dialog).toBeVisible();

  await page.getByRole("button", { name: "Keep editing", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(profileTab).toHaveAttribute("aria-selected", "true");
  await expect(displayName).toHaveValue("Unsaved Ada");

  await notificationsTab.click();
  await page.getByRole("button", { name: "Discard", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(notificationsTab).toHaveAttribute("aria-selected", "true");

  await profileTab.click();
  await expect(displayName).toHaveValue("Ada");
});
