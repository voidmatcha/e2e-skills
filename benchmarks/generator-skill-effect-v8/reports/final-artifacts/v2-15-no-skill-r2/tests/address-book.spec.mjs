import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("updates regions when country changes and clears the selected region", async ({ page }) => {
  const country = page.getByLabel("Country");
  const region = page.getByLabel("Region");

  await expect(region).toBeDisabled();
  await expect(region).toHaveValue("");

  await country.selectOption("CA");
  await expect(region).toBeEnabled();
  await expect(region.locator("option")).toHaveText([
    "Choose a region",
    "Alberta",
    "British Columbia",
    "Ontario",
    "Quebec",
  ]);

  await region.selectOption("Ontario");
  await expect(region).toHaveValue("Ontario");

  await country.selectOption("US");
  await expect(region).toHaveValue("");
  await expect(region.locator("option")).toHaveText([
    "Choose a region",
    "California",
    "New York",
    "Texas",
    "Washington",
  ]);
});

[
  { country: "CA", countryName: "Canada", region: "Ontario", badPostal: "12345" },
  { country: "DE", countryName: "Germany", region: "Berlin", badPostal: "A1A 1A1" },
  { country: "US", countryName: "United States", region: "Texas", badPostal: "1234" },
].forEach(({ country, countryName, region, badPostal }) => {
  test(`rejects an invalid postal code for ${countryName}`, async ({ page }) => {
    await page.getByLabel("Country").selectOption(country);
    await page.getByLabel("Region").selectOption(region);
    await page.getByLabel("Postal code").fill(badPostal);
    await page.getByRole("button", { name: "Save address" }).click();

    await expect(page.getByRole("alert")).toHaveText(`Enter a valid postal code for ${countryName}`);
    await expect(page.getByRole("list", { name: "Saved addresses" }).getByRole("listitem")).toHaveCount(0);
  });
});

test("saves addresses and keeps exactly one default through reloads", async ({ page }) => {
  const savedAddresses = page.getByRole("list", { name: "Saved addresses" });

  await page.getByLabel("Country").selectOption("CA");
  await page.getByLabel("Region").selectOption("Ontario");
  await page.getByLabel("Postal code").fill("A1A 1A1");
  await page.getByRole("button", { name: "Save address" }).click();

  await expect(savedAddresses.getByRole("listitem")).toHaveText([
    "Ontario, Canada A1A 1A1 (default)",
  ]);

  await page.getByLabel("Country").selectOption("US");
  await page.getByLabel("Region").selectOption("Texas");
  await page.getByLabel("Postal code").fill("12345");
  await page.getByRole("button", { name: "Save address" }).click();

  await expect(savedAddresses.getByRole("listitem")).toHaveText([
    "Ontario, Canada A1A 1A1 (default)",
    "Texas, United States 12345Set as default",
  ]);
  await expect(savedAddresses.getByText("(default)")).toHaveCount(1);

  await page.getByRole("button", { name: "Set Texas as default" }).click();

  await expect(savedAddresses.getByRole("listitem")).toHaveText([
    "Ontario, Canada A1A 1A1Set as default",
    "Texas, United States 12345 (default)",
  ]);
  await expect(savedAddresses.getByText("(default)")).toHaveCount(1);

  await page.reload();

  await expect(savedAddresses.getByRole("listitem")).toHaveText([
    "Ontario, Canada A1A 1A1Set as default",
    "Texas, United States 12345 (default)",
  ]);
  await expect(savedAddresses.getByText("(default)")).toHaveCount(1);
});
