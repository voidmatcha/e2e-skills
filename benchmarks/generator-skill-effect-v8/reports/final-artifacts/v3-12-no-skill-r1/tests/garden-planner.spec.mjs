import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const bed = (page, name) =>
  page.locator("article.bed", { has: page.getByRole("heading", { name }) });

test("shows the seeded watering state for all beds", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("article.bed")).toHaveCount(4);
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

test("watering beds updates their cards and survives a reload", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Water Bed 2" }).click();
  await expect(bed(page, "Bed 2")).toContainText("Last watered: today");
  await expect(bed(page, "Bed 2").getByText("Needs water")).toBeHidden();
  await expect(page.locator("#gp-summary")).toHaveText("1 bed needs water");

  await page.getByRole("button", { name: "Water Bed 3" }).click();
  await expect(bed(page, "Bed 3")).toContainText("Last watered: today");
  await expect(bed(page, "Bed 3").getByText("Needs water")).toBeHidden();
  await expect(page.locator("#gp-summary")).toHaveText("No beds need water");

  await page.reload();

  await expect(bed(page, "Bed 2")).toContainText("Last watered: today");
  await expect(bed(page, "Bed 2").getByText("Needs water")).toBeHidden();
  await expect(bed(page, "Bed 3")).toContainText("Last watered: today");
  await expect(bed(page, "Bed 3").getByText("Needs water")).toBeHidden();
  await expect(page.locator("#gp-summary")).toHaveText("No beds need water");
});

test("changing a bed plant updates only that bed and survives a reload", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Plant for Bed 1").selectOption("Zucchini");
  await expect(page.getByLabel("Plant for Bed 1")).toHaveValue("Zucchini");
  await expect(page.getByLabel("Plant for Bed 2")).toHaveValue("Basil");

  await page.reload();

  await expect(page.getByLabel("Plant for Bed 1")).toHaveValue("Zucchini");
  await expect(page.getByLabel("Plant for Bed 2")).toHaveValue("Basil");
});

test("filtering to thirsty beds hides watered beds and shows the empty state", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Show only beds that need water").check();

  await expect(bed(page, "Bed 1")).toBeHidden();
  await expect(bed(page, "Bed 2")).toBeVisible();
  await expect(bed(page, "Bed 3")).toBeVisible();
  await expect(bed(page, "Bed 4")).toBeHidden();
  await expect(page.locator("#gp-summary")).toHaveText("2 beds need water");
  await expect(page.getByText("All beds are watered")).toBeHidden();

  await page.getByRole("button", { name: "Water Bed 2" }).click();
  await expect(bed(page, "Bed 2")).toBeHidden();
  await expect(page.locator("#gp-summary")).toHaveText("1 bed needs water");

  await page.getByRole("button", { name: "Water Bed 3" }).click();

  await expect(page.locator("article.bed")).toHaveCount(0);
  await expect(page.locator("#gp-summary")).toHaveText("No beds need water");
  await expect(page.getByText("All beds are watered")).toBeVisible();
});
