import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

const bed = (page, name) =>
  page.locator("article").filter({ has: page.getByRole("heading", { name }) });

test("shows each bed with the correct watering status", async ({ page }) => {
  await expect(page.locator("#gp-summary")).toHaveText("2 beds need water");

  await expect(bed(page, "Bed 1")).toContainText("Last watered: yesterday");
  await expect(bed(page, "Bed 1").getByText("Needs water")).toBeHidden();

  await expect(bed(page, "Bed 2")).toContainText("Last watered: 4 days ago");
  await expect(bed(page, "Bed 2").getByText("Needs water")).toBeVisible();

  await expect(bed(page, "Bed 3")).toContainText("Last watered: 3 days ago");
  await expect(bed(page, "Bed 3").getByText("Needs water")).toBeVisible();

  await expect(bed(page, "Bed 4")).toContainText("Last watered: today");
  await expect(bed(page, "Bed 4").getByText("Needs water")).toBeHidden();
});

test("watering a bed updates the card, summary, and survives a reload", async ({ page }) => {
  await bed(page, "Bed 2").getByRole("button", { name: "Water Bed 2" }).click();

  await expect(bed(page, "Bed 2")).toContainText("Last watered: today");
  await expect(bed(page, "Bed 2").getByText("Needs water")).toBeHidden();
  await expect(page.locator("#gp-summary")).toHaveText("1 bed needs water");

  await page.reload();

  await expect(bed(page, "Bed 2")).toContainText("Last watered: today");
  await expect(bed(page, "Bed 2").getByText("Needs water")).toBeHidden();
  await expect(page.locator("#gp-summary")).toHaveText("1 bed needs water");
});

test("changing a bed plant updates that bed and survives a reload", async ({ page }) => {
  await bed(page, "Bed 1").getByLabel("Plant for Bed 1").selectOption("Kale");

  await expect(bed(page, "Bed 1").getByLabel("Plant for Bed 1")).toHaveValue("Kale");
  await expect(bed(page, "Bed 2").getByLabel("Plant for Bed 2")).toHaveValue("Basil");

  await page.reload();

  await expect(bed(page, "Bed 1").getByLabel("Plant for Bed 1")).toHaveValue("Kale");
  await expect(bed(page, "Bed 2").getByLabel("Plant for Bed 2")).toHaveValue("Basil");
});

test("filters to beds that need water and shows the empty filtered state", async ({ page }) => {
  await page.getByLabel("Show only beds that need water").check();

  await expect(page.locator("article")).toHaveCount(2);
  await expect(bed(page, "Bed 1")).toHaveCount(0);
  await expect(bed(page, "Bed 2")).toBeVisible();
  await expect(bed(page, "Bed 3")).toBeVisible();
  await expect(bed(page, "Bed 4")).toHaveCount(0);
  await expect(page.getByText("All beds are watered")).toBeHidden();

  await bed(page, "Bed 2").getByRole("button", { name: "Water Bed 2" }).click();
  await bed(page, "Bed 3").getByRole("button", { name: "Water Bed 3" }).click();

  await expect(page.locator("article")).toHaveCount(0);
  await expect(page.locator("#gp-summary")).toHaveText("No beds need water");
  await expect(page.getByText("All beds are watered")).toBeVisible();
});
