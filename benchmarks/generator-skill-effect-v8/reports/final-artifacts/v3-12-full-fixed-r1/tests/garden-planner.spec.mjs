import { expect, test } from "@playwright/test";

const bedCard = (page, name) =>
  page.getByRole("article").filter({ has: page.getByRole("heading", { name: new RegExp(`^${name}$`) }) });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /^Garden planner$/ })).toBeVisible();
});

test("shows seeded water status for all beds", async ({ page }) => {
  await expect(page.getByText("2 beds need water")).toBeVisible();

  await expect(bedCard(page, "Bed 1").getByText("Last watered: yesterday")).toBeVisible();
  await expect(bedCard(page, "Bed 1").getByText("Needs water")).toBeHidden();

  await expect(bedCard(page, "Bed 2").getByText("Last watered: 4 days ago")).toBeVisible();
  await expect(bedCard(page, "Bed 2").getByText("Needs water")).toBeVisible();

  await expect(bedCard(page, "Bed 3").getByText("Last watered: 3 days ago")).toBeVisible();
  await expect(bedCard(page, "Bed 3").getByText("Needs water")).toBeVisible();

  await expect(bedCard(page, "Bed 4").getByText("Last watered: today")).toBeVisible();
  await expect(bedCard(page, "Bed 4").getByText("Needs water")).toBeHidden();
});

test("watering beds updates status and survives reload", async ({ page }) => {
  const bed2Watered = page.waitForResponse(
    (response) => response.url().endsWith("/api/beds/2/water") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /^Water Bed 2$/ }).click();
  await expect((await bed2Watered).ok()).toBe(true);

  await expect(bedCard(page, "Bed 2").getByText("Last watered: today")).toBeVisible();
  await expect(bedCard(page, "Bed 2").getByText("Needs water")).toBeHidden();
  await expect(page.getByText("1 bed needs water")).toBeVisible();

  const bed3Watered = page.waitForResponse(
    (response) => response.url().endsWith("/api/beds/3/water") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /^Water Bed 3$/ }).click();
  await expect((await bed3Watered).ok()).toBe(true);
  await expect(page.getByText("No beds need water")).toBeVisible();

  await page.reload();
  await expect(bedCard(page, "Bed 2").getByText("Last watered: today")).toBeVisible();
  await expect(bedCard(page, "Bed 3").getByText("Last watered: today")).toBeVisible();
  await expect(page.getByText("No beds need water")).toBeVisible();
});

test("plant choices update the selected bed and survive reload", async ({ page }) => {
  const plantChanged = page.waitForResponse(
    (response) => response.url().endsWith("/api/beds/1") && response.request().method() === "PATCH",
  );
  await page.getByLabel("Plant for Bed 1").selectOption("Kale");
  await expect((await plantChanged).ok()).toBe(true);

  await expect(page.getByLabel("Plant for Bed 1")).toHaveValue("Kale");

  await page.reload();
  await expect(page.getByLabel("Plant for Bed 1")).toHaveValue("Kale");
  await expect(page.getByLabel("Plant for Bed 2")).toHaveValue("Basil");
});

test("needs-water filter hides watered beds and shows empty state", async ({ page }) => {
  await page.getByLabel("Show only beds that need water").check();

  await expect(bedCard(page, "Bed 1")).toHaveCount(0);
  await expect(bedCard(page, "Bed 2")).toBeVisible();
  await expect(bedCard(page, "Bed 3")).toBeVisible();
  await expect(bedCard(page, "Bed 4")).toHaveCount(0);

  const bed2Watered = page.waitForResponse(
    (response) => response.url().endsWith("/api/beds/2/water") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /^Water Bed 2$/ }).click();
  await expect((await bed2Watered).ok()).toBe(true);
  await expect(bedCard(page, "Bed 2")).toHaveCount(0);
  await expect(bedCard(page, "Bed 3")).toBeVisible();

  const bed3Watered = page.waitForResponse(
    (response) => response.url().endsWith("/api/beds/3/water") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /^Water Bed 3$/ }).click();
  await expect((await bed3Watered).ok()).toBe(true);

  await expect(page.getByRole("article")).toHaveCount(0);
  await expect(page.getByText("All beds are watered")).toBeVisible();
  await expect(page.getByText("No beds need water")).toBeVisible();
});
