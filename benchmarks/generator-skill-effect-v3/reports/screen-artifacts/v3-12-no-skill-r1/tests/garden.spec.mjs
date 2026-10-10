import { expect, test } from "@playwright/test";

const bed = (page, name) => page.locator("article", { has: page.getByRole("heading", { name }) });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Bed 1" })).toBeVisible();
});

test("shows the seeded beds and summary", async ({ page }) => {
  await expect(page.locator("#gp-summary")).toHaveText("2 beds need water");
  await expect(bed(page, "Bed 1").getByText("Last watered: yesterday")).toBeVisible();
  await expect(bed(page, "Bed 2").getByText("Last watered: 4 days ago")).toBeVisible();
  await expect(bed(page, "Bed 3").getByText("Last watered: 3 days ago")).toBeVisible();
  await expect(bed(page, "Bed 4").getByText("Last watered: today")).toBeVisible();
  await expect(bed(page, "Bed 1").getByText("Needs water")).toBeHidden();
  await expect(bed(page, "Bed 2").getByText("Needs water")).toBeVisible();
  await expect(bed(page, "Bed 3").getByText("Needs water")).toBeVisible();
  await expect(bed(page, "Bed 4").getByText("Needs water")).toBeHidden();
});

test("watering a bed updates it and the summary", async ({ page }) => {
  await page.getByRole("button", { name: "Water Bed 2" }).click();
  await expect(bed(page, "Bed 2").getByText("Last watered: today")).toBeVisible();
  await expect(bed(page, "Bed 2").getByText("Needs water")).toBeHidden();
  await expect(page.locator("#gp-summary")).toHaveText("1 bed needs water");
  await page.getByRole("button", { name: "Water Bed 3" }).click();
  await expect(page.locator("#gp-summary")).toHaveText("No beds need water");
});

test("choosing a plant changes only that bed", async ({ page }) => {
  await page.getByLabel("Plant for Bed 1").selectOption("Kale");
  await expect(page.getByLabel("Plant for Bed 1")).toHaveValue("Kale");
  await expect(page.getByLabel("Plant for Bed 2")).toHaveValue("Basil");
});

test("filter shows only beds that need water", async ({ page }) => {
  await page.getByLabel("Show only beds that need water").check();
  await expect(page.getByRole("heading", { name: "Bed 2" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Bed 3" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Bed 1" })).toBeHidden();
  await expect(page.getByRole("heading", { name: "Bed 4" })).toBeHidden();
  await expect(page.getByText("All beds are watered")).toBeHidden();
});

test("filter shows the all-watered message once no bed needs water", async ({ page }) => {
  await page.getByLabel("Show only beds that need water").check();
  await page.getByRole("button", { name: "Water Bed 2" }).click();
  await expect(page.getByRole("heading", { name: "Bed 2" })).toBeHidden();
  await page.getByRole("button", { name: "Water Bed 3" }).click();
  await expect(page.getByText("All beds are watered")).toBeVisible();
  await expect(page.locator("#gp-summary")).toHaveText("No beds need water");
  await page.getByLabel("Show only beds that need water").uncheck();
  await expect(page.getByText("All beds are watered")).toBeHidden();
  await expect(page.getByRole("heading", { name: "Bed 1" })).toBeVisible();
});

test("watering and plant choices survive a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Water Bed 2" }).click();
  await expect(bed(page, "Bed 2").getByText("Last watered: today")).toBeVisible();
  await page.getByLabel("Plant for Bed 4").selectOption("Basil");
  await expect(page.getByLabel("Plant for Bed 4")).toHaveValue("Basil");
  await page.reload();
  await expect(bed(page, "Bed 2").getByText("Last watered: today")).toBeVisible();
  await expect(page.locator("#gp-summary")).toHaveText("1 bed needs water");
  await expect(page.getByLabel("Plant for Bed 4")).toHaveValue("Basil");
});
