import { expect, test } from "@playwright/test";

const bed = (page, name) => page.getByRole("article").filter({ has: page.getByRole("heading", { name }) });
const summary = (page) => page.getByText(/^(\d+ beds? needs? water|No beds need water)$/);

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(summary(page)).toHaveText("2 beds need water");
});

test("watering updates the line, the badge and the summary, and persists", async ({ page }) => {
  await expect(bed(page, "Bed 2")).toContainText("Last watered: 4 days ago");
  await expect(bed(page, "Bed 2").getByText("Needs water")).toBeVisible();
  await page.getByRole("button", { name: "Water Bed 2" }).click();
  await expect(bed(page, "Bed 2")).toContainText("Last watered: today");
  await expect(bed(page, "Bed 2").getByText("Needs water")).toBeHidden();
  await expect(summary(page)).toHaveText("1 bed needs water");
  await page.reload();
  await expect(bed(page, "Bed 2")).toContainText("Last watered: today");
  await expect(summary(page)).toHaveText("1 bed needs water");
});

test("plant choice persists", async ({ page }) => {
  await page.getByRole("combobox", { name: "Plant for Bed 1" }).selectOption("Kale");
  await expect(page.getByRole("combobox", { name: "Plant for Bed 1" })).toHaveValue("Kale");
  await page.reload();
  await expect(page.getByRole("combobox", { name: "Plant for Bed 1" })).toHaveValue("Kale");
});

test("the filter shows only thirsty beds and the all-watered message", async ({ page }) => {
  await page.getByLabel("Show only beds that need water").check();
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(bed(page, "Bed 2")).toBeVisible();
  await expect(bed(page, "Bed 3")).toBeVisible();
  await expect(page.getByText("All beds are watered")).toBeHidden();
  await page.getByRole("button", { name: "Water Bed 2" }).click();
  await page.getByRole("button", { name: "Water Bed 3" }).click();
  await expect(page.getByRole("article")).toHaveCount(0);
  await expect(page.getByText("All beds are watered")).toBeVisible();
  await expect(summary(page)).toHaveText("No beds need water");
  await page.getByLabel("Show only beds that need water").uncheck();
  await expect(page.getByRole("article")).toHaveCount(4);
  await expect(page.getByText("All beds are watered")).toBeHidden();
});
