import { expect, test } from "@playwright/test";

const regions = {
  Canada: ["Alberta", "British Columbia", "Ontario", "Quebec"],
  Germany: ["Bavaria", "Berlin", "Hamburg", "Saxony"],
  "United States": ["California", "New York", "Texas", "Washington"],
};

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

async function expectRegionOptions(page, country) {
  const region = page.getByLabel("Region");
  await expect(region).toBeEnabled();
  await expect(region.locator("option")).toHaveText(["Choose a region", ...regions[country]]);
}

async function saveAddress(page, { country, region, postal }) {
  await page.getByLabel("Country").selectOption({ label: country });
  await page.getByLabel("Region").selectOption({ label: region });
  await page.getByLabel("Postal code").fill(postal);
  await page.getByRole("button", { name: "Save address" }).click();
}

test("choosing a country fills regions and changing country clears the region", async ({ page }) => {
  const region = page.getByLabel("Region");

  await expect(region).toBeDisabled();
  await expect(region.locator("option")).toHaveText(["Choose a region"]);

  await page.getByLabel("Country").selectOption({ label: "Canada" });
  await expectRegionOptions(page, "Canada");
  await region.selectOption({ label: "Ontario" });
  await expect(region).toHaveValue("Ontario");

  await page.getByLabel("Country").selectOption({ label: "Germany" });
  await expectRegionOptions(page, "Germany");
  await expect(region).toHaveValue("");
});

for (const { country, region, postal } of [
  { country: "Canada", region: "Ontario", postal: "12345" },
  { country: "Germany", region: "Berlin", postal: "A1A 1A1" },
  { country: "United States", region: "Texas", postal: "1234" },
]) {
  test(`rejects an invalid postal code for ${country}`, async ({ page }) => {
    await saveAddress(page, { country, region, postal });

    await expect(page.getByRole("alert")).toHaveText(`Enter a valid postal code for ${country}`);
    await expect(page.getByRole("list", { name: "Saved addresses" }).getByRole("listitem")).toHaveCount(0);
  });
}

test("lists saved addresses and keeps exactly one default across reloads", async ({ page }) => {
  const list = page.getByRole("list", { name: "Saved addresses" });

  await saveAddress(page, { country: "Canada", region: "Ontario", postal: "A1A 1A1" });
  await expect(list.getByRole("listitem")).toHaveText(["Ontario, Canada A1A 1A1 (default)"]);

  await saveAddress(page, { country: "United States", region: "New York", postal: "10001" });
  await expect(list.getByRole("listitem")).toHaveText([
    "Ontario, Canada A1A 1A1 (default)",
    "New York, United States 10001Set as default",
  ]);

  await list.getByRole("button", { name: "Set New York as default" }).click();
  await expect(list.getByRole("listitem")).toHaveText([
    "Ontario, Canada A1A 1A1Set as default",
    "New York, United States 10001 (default)",
  ]);
  await expect(list.locator(".default")).toHaveCount(1);

  await page.reload();
  await expect(list.getByRole("listitem")).toHaveText([
    "Ontario, Canada A1A 1A1Set as default",
    "New York, United States 10001 (default)",
  ]);
  await expect(list.locator(".default")).toHaveCount(1);
});
