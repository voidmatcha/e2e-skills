import { expect, test } from "@playwright/test";

const dialog = (page) => page.getByRole("dialog", { name: "Delete your account?" });
const open = (page) => page.getByRole("button", { name: "Delete account" });
const confirm = (page) => page.getByRole("button", { name: "Delete my account" });
const box = (page) => page.getByLabel("Type DELETE to confirm");

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("ada@example.com")).toBeVisible();
});

test("the confirm button needs exactly DELETE", async ({ page }) => {
  await open(page).click();
  await expect(dialog(page)).toBeVisible();
  await expect(confirm(page)).toBeDisabled();
  await box(page).fill("delete");
  await expect(confirm(page)).toBeDisabled();
  await box(page).fill("DELET");
  await expect(confirm(page)).toBeDisabled();
  await box(page).fill("DELETE");
  await expect(confirm(page)).toBeEnabled();
});

test("escape and cancel close without deleting and restore focus", async ({ page }) => {
  await open(page).click();
  await expect(dialog(page)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog(page)).toBeHidden();
  await expect(open(page)).toBeFocused();
  await expect(page.getByText("ada@example.com")).toBeVisible();
  await open(page).click();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog(page)).toBeHidden();
  await expect(open(page)).toBeFocused();
  await page.reload();
  await expect(page.getByText("ada@example.com")).toBeVisible();
});

test("confirming deletes on the server", async ({ page }) => {
  await open(page).click();
  await box(page).fill("DELETE");
  await confirm(page).click();
  await expect(page.getByRole("status")).toHaveText("Your account has been deleted");
  await expect(page.getByText("ada@example.com")).toBeHidden();
  await page.reload();
  await expect(page.getByRole("status")).toHaveText("Your account has been deleted");
  await expect(page.getByText("ada@example.com")).toBeHidden();
});
