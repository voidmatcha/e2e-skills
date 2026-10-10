import { expect, test } from "@playwright/test";

const bedCard = (page, name) =>
  page.getByRole("article").filter({ has: page.getByRole("heading", { name, exact: true }) });

const resetGarden = async (page) => {
  const response = await page.request.post("/api/reset");
  expect(response.ok()).toBe(true);
};

const waterBed = async (page, bedId) => {
  const requestPromise = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === `/api/beds/${bedId}/water`,
  );

  await page.getByRole("button", { name: `Water Bed ${bedId}`, exact: true }).click();

  return requestPromise;
};

test.beforeEach(async ({ page }) => {
  await resetGarden(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Garden planner", exact: true })).toBeVisible();
});

test("shows the seeded watering state and persists watering a bed", async ({ page }) => {
  await expect(page.getByText("2 beds need water")).toBeVisible();
  await expect(page.getByRole("article")).toHaveCount(4);
  await expect(bedCard(page, "Bed 1").getByText("Last watered: yesterday")).toBeVisible();
  await expect(bedCard(page, "Bed 2").getByText("Last watered: 4 days ago")).toBeVisible();
  await expect(bedCard(page, "Bed 2").getByText("Needs water")).toBeVisible();
  await expect(bedCard(page, "Bed 3").getByText("Last watered: 3 days ago")).toBeVisible();
  await expect(bedCard(page, "Bed 3").getByText("Needs water")).toBeVisible();
  await expect(bedCard(page, "Bed 4").getByText("Last watered: today")).toBeVisible();

  const request = await waterBed(page, 2);
  expect(request.postData()).toBeNull();

  await expect(bedCard(page, "Bed 2").getByText("Last watered: today")).toBeVisible();
  await expect(bedCard(page, "Bed 2").getByText("Needs water")).toBeHidden();
  await expect(page.getByText("1 bed needs water")).toBeVisible();

  await page.reload();

  await expect(bedCard(page, "Bed 2").getByText("Last watered: today")).toBeVisible();
  await expect(bedCard(page, "Bed 2").getByText("Needs water")).toBeHidden();
  await expect(page.getByText("1 bed needs water")).toBeVisible();
});

test("persists plant choices for a bed", async ({ page }) => {
  const plantSelect = page.getByRole("combobox", { name: "Plant for Bed 1", exact: true });
  const requestPromise = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" && new URL(request.url()).pathname === "/api/beds/1",
  );

  await plantSelect.selectOption("Zucchini");
  const request = await requestPromise;

  expect(JSON.parse(request.postData())).toEqual({ plant: "Zucchini" });
  await expect(plantSelect).toHaveValue("Zucchini");

  await page.reload();

  await expect(page.getByRole("combobox", { name: "Plant for Bed 1", exact: true })).toHaveValue(
    "Zucchini",
  );
});

test("filters to beds that need water and shows the empty state when all are watered", async ({
  page,
}) => {
  await page
    .getByRole("checkbox", { name: "Show only beds that need water", exact: true })
    .check();

  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(bedCard(page, "Bed 2")).toBeVisible();
  await expect(bedCard(page, "Bed 3")).toBeVisible();
  await expect(bedCard(page, "Bed 1")).toBeHidden();
  await expect(bedCard(page, "Bed 4")).toBeHidden();

  await waterBed(page, 2);
  await expect(page.getByRole("article")).toHaveCount(1);
  await expect(bedCard(page, "Bed 3")).toBeVisible();

  await waterBed(page, 3);

  await expect(page.getByText("No beds need water")).toBeVisible();
  await expect(page.getByText("All beds are watered")).toBeVisible();
  await expect(page.getByRole("article")).toHaveCount(0);
});
