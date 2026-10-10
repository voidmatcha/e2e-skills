import { expect, test } from "@playwright/test";

const bedCard = (page, name) =>
  page.getByRole("article").filter({ has: page.getByRole("heading", { name }) });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("shows the seeded watering status for all beds", async ({ page }) => {
  await expect(page.getByText("2 beds need water")).toBeVisible();
  await expect(page.getByRole("article")).toHaveCount(4);

  const bed1 = bedCard(page, "Bed 1");
  await expect(bed1.getByText("Last watered: yesterday")).toBeVisible();
  await expect(bed1.getByText("Needs water")).toBeHidden();

  const bed2 = bedCard(page, "Bed 2");
  await expect(bed2.getByText("Last watered: 4 days ago")).toBeVisible();
  await expect(bed2.getByText("Needs water")).toBeVisible();

  const bed3 = bedCard(page, "Bed 3");
  await expect(bed3.getByText("Last watered: 3 days ago")).toBeVisible();
  await expect(bed3.getByText("Needs water")).toBeVisible();

  const bed4 = bedCard(page, "Bed 4");
  await expect(bed4.getByText("Last watered: today")).toBeVisible();
  await expect(bed4.getByText("Needs water")).toBeHidden();
});

test("waters a thirsty bed and keeps the update after reload", async ({ page }) => {
  const waterRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/beds/2/water",
  );

  await bedCard(page, "Bed 2").getByRole("button", { name: "Water Bed 2" }).click();
  await waterRequest;

  const bed2 = bedCard(page, "Bed 2");
  await expect(bed2.getByText("Last watered: today")).toBeVisible();
  await expect(bed2.getByText("Needs water")).toBeHidden();
  await expect(page.getByText("1 bed needs water")).toBeVisible();

  await page.reload();
  await expect(bedCard(page, "Bed 2").getByText("Last watered: today")).toBeVisible();
});

test("changes a bed plant and keeps the choice after reload", async ({ page }) => {
  const plantRequest = page.waitForRequest((request) => {
    if (request.method() !== "PATCH" || new URL(request.url()).pathname !== "/api/beds/2") {
      return false;
    }

    return JSON.parse(request.postData() ?? "{}").plant === "Zucchini";
  });

  await page.getByLabel("Plant for Bed 2").selectOption("Zucchini");
  await plantRequest;

  await expect(page.getByLabel("Plant for Bed 2")).toHaveValue("Zucchini");

  await page.reload();
  await expect(page.getByLabel("Plant for Bed 2")).toHaveValue("Zucchini");
});

test("filters to thirsty beds and shows the empty filtered state after watering", async ({ page }) => {
  await page.getByLabel("Show only beds that need water").check();

  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(bedCard(page, "Bed 1")).toBeHidden();
  await expect(bedCard(page, "Bed 2")).toBeVisible();
  await expect(bedCard(page, "Bed 3")).toBeVisible();
  await expect(bedCard(page, "Bed 4")).toBeHidden();

  const bed2WaterRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/beds/2/water",
  );
  await bedCard(page, "Bed 2").getByRole("button", { name: "Water Bed 2" }).click();
  await bed2WaterRequest;

  const bed3WaterRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/beds/3/water",
  );
  await bedCard(page, "Bed 3").getByRole("button", { name: "Water Bed 3" }).click();
  await bed3WaterRequest;

  await expect(page.getByText("No beds need water")).toBeVisible();
  await expect(page.getByText("All beds are watered")).toBeVisible();
  await expect(page.getByRole("article")).toHaveCount(0);
});
