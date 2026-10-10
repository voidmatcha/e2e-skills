import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const saveAddress = async (page, { country, region, postal }) => {
  await page.getByLabel("Country").selectOption(country);
  await page.getByLabel("Region").selectOption(region);
  await page.getByLabel("Postal code").fill(postal);
  await page.getByRole("button", { name: "Save address" }).click();
};

const expectRegionOptions = async (region, values) => {
  await expect.poll(() => region.locator("option").evaluateAll((options) => options.map((option) => option.value))).toEqual(values);
};

test("choosing a country fills regions and clears the previous region", async ({ page }) => {
  await page.goto("/");

  const country = page.getByLabel("Country");
  const region = page.getByLabel("Region");

  await expect(region).toBeDisabled();

  await country.selectOption("CA");
  await expect(region).toBeEnabled();
  await expectRegionOptions(region, ["", "Alberta", "British Columbia", "Ontario", "Quebec"]);

  await region.selectOption("Ontario");
  await expect(region).toHaveValue("Ontario");

  await country.selectOption("DE");
  await expect(region).toBeEnabled();
  await expect(region).toHaveValue("");
  await expectRegionOptions(region, ["", "Bavaria", "Berlin", "Hamburg", "Saxony"]);
});

test("validates postal codes for each country before saving", async ({ page }) => {
  await page.goto("/");

  const cases = [
    { country: "CA", countryName: "Canada", region: "Ontario", badPostal: "12345" },
    { country: "DE", countryName: "Germany", region: "Berlin", badPostal: "A1A 1A1" },
    { country: "US", countryName: "United States", region: "Texas", badPostal: "1234" },
  ];

  for (const entry of cases) {
    await saveAddress(page, {
      country: entry.country,
      region: entry.region,
      postal: entry.badPostal,
    });

    await expect(page.getByRole("alert")).toHaveText(`Enter a valid postal code for ${entry.countryName}`);
    await expect(page.getByRole("list", { name: "Saved addresses" }).getByRole("listitem")).toHaveCount(0);
  }
});

test("lists saved addresses and keeps exactly one default across reloads", async ({ page }) => {
  await page.goto("/");

  await saveAddress(page, { country: "CA", region: "Quebec", postal: "A1A 1A1" });
  await expect(page.getByRole("listitem").filter({ hasText: "Quebec, Canada A1A 1A1" })).toContainText("(default)");

  await saveAddress(page, { country: "US", region: "Texas", postal: "75001" });
  await expect(page.getByRole("listitem")).toHaveCount(2);
  await expect(page.getByRole("listitem").filter({ hasText: "Quebec, Canada A1A 1A1" })).toContainText("(default)");
  await expect(page.getByRole("listitem").filter({ hasText: "Texas, United States 75001" })).not.toContainText("(default)");

  await page.getByRole("button", { name: "Set Texas as default" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Quebec, Canada A1A 1A1" })).not.toContainText("(default)");
  await expect(page.getByRole("listitem").filter({ hasText: "Texas, United States 75001" })).toContainText("(default)");
  await expect(page.getByText("(default)")).toHaveCount(1);

  await page.reload();
  await expect(page.getByRole("listitem")).toHaveCount(2);
  await expect(page.getByRole("listitem").filter({ hasText: "Quebec, Canada A1A 1A1" })).not.toContainText("(default)");
  await expect(page.getByRole("listitem").filter({ hasText: "Texas, United States 75001" })).toContainText("(default)");
  await expect(page.getByText("(default)")).toHaveCount(1);
});
