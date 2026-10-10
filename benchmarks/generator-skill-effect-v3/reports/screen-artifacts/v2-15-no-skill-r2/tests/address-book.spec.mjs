import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

async function save(page, country, region, postal) {
  await page.getByLabel("Country").selectOption({ label: country });
  await page.getByLabel("Region").selectOption(region);
  await page.getByLabel("Postal code").fill(postal);
  await page.getByRole("button", { name: "Save address" }).click();
}

const items = (page) => page.getByRole("list", { name: "Saved addresses" }).getByRole("listitem");

test("choosing a country fills its regions and clears the chosen region", async ({ page }) => {
  const region = page.getByLabel("Region");
  await expect(region).toBeDisabled();
  await page.getByLabel("Country").selectOption({ label: "Canada" });
  await expect(region.getByRole("option")).toHaveText(["Choose a region", "Alberta", "British Columbia", "Ontario", "Quebec"]);
  await region.selectOption("Ontario");
  await expect(region).toHaveValue("Ontario");
  await page.getByLabel("Country").selectOption({ label: "Germany" });
  await expect(region).toHaveValue("");
  await expect(region.getByRole("option")).toHaveText(["Choose a region", "Bavaria", "Berlin", "Hamburg", "Saxony"]);
});

const invalid = [
  ["Canada", "Ontario", "12345"],
  ["Canada", "Ontario", "K1A1A1"],
  ["Germany", "Berlin", "1234"],
  ["Germany", "Berlin", "123456"],
  ["United States", "Texas", "1234a"],
];
for (const [country, region, postal] of invalid) {
  test(`rejects postal code "${postal}" for ${country}`, async ({ page }) => {
    await save(page, country, region, postal);
    await expect(page.getByRole("alert")).toHaveText(`Enter a valid postal code for ${country}`);
    await expect(items(page)).toHaveCount(0);
    await page.reload();
    await expect(items(page)).toHaveCount(0);
  });
}

test("accepts valid postal codes and lists the addresses", async ({ page }) => {
  await save(page, "Canada", "Ontario", "K1A 1A1");
  await expect(items(page)).toHaveCount(1);
  await save(page, "Germany", "Berlin", "10115");
  await save(page, "United States", "Texas", "73301");
  await expect(items(page)).toHaveCount(3);
  await expect(page.getByRole("alert")).toHaveText("");
  await expect(items(page).nth(1)).toContainText("Berlin, Germany 10115");
});

test("first saved address is the default and Set as default moves it", async ({ page }) => {
  await save(page, "Canada", "Ontario", "K1A 1A1");
  await save(page, "Germany", "Berlin", "10115");
  await save(page, "United States", "Texas", "73301");
  await expect(items(page).filter({ hasText: "(default)" })).toHaveCount(1);
  await expect(items(page).nth(0)).toContainText("(default)");

  await page.getByRole("button", { name: "Set Texas as default" }).click();
  await expect(items(page).filter({ hasText: "(default)" })).toHaveCount(1);
  await expect(items(page).nth(2)).toContainText("(default)");
  await expect(items(page).nth(0)).not.toContainText("(default)");
  await expect(page.getByRole("button", { name: "Set Ontario as default" })).toBeVisible();

  await page.reload();
  await expect(items(page)).toHaveCount(3);
  await expect(items(page).filter({ hasText: "(default)" })).toHaveCount(1);
  await expect(items(page).nth(2)).toContainText("(default)");
});
