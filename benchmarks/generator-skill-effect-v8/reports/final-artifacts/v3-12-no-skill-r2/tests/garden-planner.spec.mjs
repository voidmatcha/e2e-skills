import { expect, test } from "@playwright/test";

const bed = (page, name) =>
  page.locator("article").filter({ has: page.getByRole("heading", { name }) });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
});

test("shows seeded beds with water status and summary", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("2 beds need water")).toBeVisible();
  await expect(bed(page, "Bed 1")).toContainText("Last watered: yesterday");
  await expect(bed(page, "Bed 2")).toContainText("Last watered: 4 days ago");
  await expect(bed(page, "Bed 3")).toContainText("Last watered: 3 days ago");
  await expect(bed(page, "Bed 4")).toContainText("Last watered: today");

  await expect(bed(page, "Bed 1").getByText("Needs water")).toBeHidden();
  await expect(bed(page, "Bed 2").getByText("Needs water")).toBeVisible();
  await expect(bed(page, "Bed 3").getByText("Needs water")).toBeVisible();
  await expect(bed(page, "Bed 4").getByText("Needs water")).toBeHidden();
});

test("watering beds updates status, summary, filter, and survives reload", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Water Bed 2" }).click();
  await expect(bed(page, "Bed 2")).toContainText("Last watered: today");
  await expect(bed(page, "Bed 2").getByText("Needs water")).toBeHidden();
  await expect(page.getByText("1 bed needs water")).toBeVisible();

  await page.getByRole("checkbox", { name: "Show only beds that need water" }).check();
  await expect(bed(page, "Bed 1")).toBeHidden();
  await expect(bed(page, "Bed 2")).toBeHidden();
  await expect(bed(page, "Bed 3")).toBeVisible();
  await expect(bed(page, "Bed 4")).toBeHidden();
  await expect(page.getByText("All beds are watered")).toBeHidden();

  await page.getByRole("button", { name: "Water Bed 3" }).click();
  await expect(page.getByText("No beds need water")).toBeVisible();
  await expect(page.getByText("All beds are watered")).toBeVisible();
  await expect(page.locator("article")).toHaveCount(0);

  await page.reload();
  await expect(page.getByText("No beds need water")).toBeVisible();
  await expect(bed(page, "Bed 2")).toContainText("Last watered: today");
  await expect(bed(page, "Bed 3")).toContainText("Last watered: today");

  await page.getByRole("checkbox", { name: "Show only beds that need water" }).check();
  await expect(page.getByText("All beds are watered")).toBeVisible();
  await expect(page.locator("article")).toHaveCount(0);
});

test("plant choices update the bed and survive reload", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Plant for Bed 1").selectOption("Kale");
  await expect(page.getByLabel("Plant for Bed 1")).toHaveValue("Kale");
  await expect(page.getByLabel("Plant for Bed 2")).toHaveValue("Basil");

  await page.reload();
  await expect(page.getByLabel("Plant for Bed 1")).toHaveValue("Kale");
  await expect(page.getByLabel("Plant for Bed 2")).toHaveValue("Basil");
});
