import { expect, test } from "@playwright/test";

test("toggles the chosen item once and persists saved state", async ({ page }) => {
  await page.goto("/");
  const oak = page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "Toggle Oak" }) });
  const cedar = page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "Toggle Cedar" }) });
  await expect(page.getByRole("status")).toHaveText("Saved: 0");
  await expect(oak).toContainText("Oak: Not saved");
  await expect(cedar).toContainText("Cedar: Not saved");

  await page.getByRole("button", { name: "Toggle Oak" }).click();
  await expect(page.getByRole("status")).toHaveText("Saved: 1");
  await expect(oak).toContainText("Oak: Saved");
  await expect(cedar).toContainText("Cedar: Not saved");

  await page.getByRole("button", { name: "Toggle Cedar" }).click();
  await expect(page.getByRole("status")).toHaveText("Saved: 2");
  await expect(oak).toContainText("Oak: Saved");
  await expect(cedar).toContainText("Cedar: Saved");

  await page.reload();
  await expect(page.getByRole("status")).toHaveText("Saved: 2");
  await expect(oak).toContainText("Oak: Saved");
  await expect(cedar).toContainText("Cedar: Saved");

  await page.getByRole("button", { name: "Toggle Oak" }).click();
  await expect(page.getByRole("status")).toHaveText("Saved: 1");
  await expect(oak).toContainText("Oak: Not saved");
  await expect(cedar).toContainText("Cedar: Saved");
});
