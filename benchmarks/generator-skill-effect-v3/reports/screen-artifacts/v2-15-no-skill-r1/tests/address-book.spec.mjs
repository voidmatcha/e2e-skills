import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
});

const addresses = (page) => page.getByRole("list", { name: "Saved addresses" }).getByRole("listitem");

async function save(page, { country, region, postal }) {
  await page.getByLabel("Country").selectOption({ label: country });
  await page.getByLabel("Region").selectOption({ label: region });
  await page.getByLabel("Postal code").fill(postal);
  await page.getByRole("button", { name: "Save address" }).click();
}

test.describe("country and region", () => {
  test("region list is disabled until a country is chosen", async ({ page }) => {
    await expect(page.getByLabel("Region")).toBeDisabled();
  });

  for (const [country, regions] of [
    ["Canada", ["Alberta", "British Columbia", "Ontario", "Quebec"]],
    ["Germany", ["Bavaria", "Berlin", "Hamburg", "Saxony"]],
    ["United States", ["California", "New York", "Texas", "Washington"]],
  ]) {
    test(`choosing ${country} fills its regions`, async ({ page }) => {
      await page.getByLabel("Country").selectOption({ label: country });
      const region = page.getByLabel("Region");
      await expect(region).toBeEnabled();
      await expect(region.locator("option")).toHaveText(["Choose a region", ...regions]);
    });
  }

  test("changing country replaces regions and clears the chosen region", async ({ page }) => {
    const region = page.getByLabel("Region");
    await page.getByLabel("Country").selectOption({ label: "Canada" });
    await region.selectOption({ label: "Ontario" });
    await expect(region).toHaveValue("Ontario");

    await page.getByLabel("Country").selectOption({ label: "Germany" });
    await expect(region).toHaveValue("");
    await expect(region.locator("option")).toHaveText(["Choose a region", "Bavaria", "Berlin", "Hamburg", "Saxony"]);
    await expect(region.locator("option", { hasText: "Ontario" })).toHaveCount(0);
  });

  test("returning to the placeholder country empties and disables regions", async ({ page }) => {
    const region = page.getByLabel("Region");
    await page.getByLabel("Country").selectOption({ label: "Canada" });
    await region.selectOption({ label: "Quebec" });
    await page.getByLabel("Country").selectOption({ label: "Choose a country" });
    await expect(region).toBeDisabled();
    await expect(region).toHaveValue("");
    await expect(region.locator("option")).toHaveText(["Choose a region"]);
  });
});

test.describe("postal code validation", () => {
  const invalid = [
    ["Canada", "Ontario", "12345"],
    ["Canada", "Ontario", "A1A1A1"],
    ["Canada", "Ontario", "1A1 A1A"],
    ["Germany", "Berlin", "1234"],
    ["Germany", "Berlin", "123456"],
    ["Germany", "Berlin", "A1A 1A1"],
    ["United States", "Texas", "1234a"],
    ["United States", "Texas", "123456"],
    ["United States", "Texas", ""],
  ];
  for (const [country, region, postal] of invalid) {
    test(`rejects "${postal}" for ${country}`, async ({ page }) => {
      await save(page, { country, region, postal });
      await expect(page.getByRole("alert")).toHaveText(`Enter a valid postal code for ${country}`);
      await expect(addresses(page)).toHaveCount(0);
      // The form keeps the user's input so they can correct it.
      await expect(page.getByLabel("Region")).toHaveValue(region);
      await expect(page.getByLabel("Postal code")).toHaveValue(postal);
    });
  }

  const valid = [
    ["Canada", "Ontario", "K1A 0B1"],
    ["Germany", "Berlin", "10115"],
    ["United States", "Texas", "73301"],
  ];
  for (const [country, region, postal] of valid) {
    test(`accepts "${postal}" for ${country}`, async ({ page }) => {
      await save(page, { country, region, postal });
      await expect(addresses(page)).toHaveCount(1);
      await expect(addresses(page).first()).toContainText(`${region}, ${country} ${postal}`);
      await expect(page.getByRole("alert")).toHaveText("");
    });
  }

  test("an error clears after a successful save", async ({ page }) => {
    await save(page, { country: "Germany", region: "Berlin", postal: "abc" });
    await expect(page.getByRole("alert")).toHaveText("Enter a valid postal code for Germany");
    await page.getByLabel("Postal code").fill("10115");
    await page.getByRole("button", { name: "Save address" }).click();
    await expect(addresses(page)).toHaveCount(1);
    await expect(page.getByRole("alert")).toHaveText("");
  });

  test("a rejected address is not persisted across reload", async ({ page }) => {
    await save(page, { country: "Canada", region: "Alberta", postal: "nope" });
    await expect(page.getByRole("alert")).toHaveText("Enter a valid postal code for Canada");
    await page.reload();
    await expect(addresses(page)).toHaveCount(0);
  });
});

test.describe("saved addresses and default", () => {
  test("a successful save resets the form", async ({ page }) => {
    await save(page, { country: "Canada", region: "Ontario", postal: "K1A 0B1" });
    await expect(addresses(page)).toHaveCount(1);
    await expect(page.getByLabel("Country")).toHaveValue("");
    await expect(page.getByLabel("Region")).toBeDisabled();
    await expect(page.getByLabel("Postal code")).toHaveValue("");
  });

  test("the first saved address is the default, later ones are not", async ({ page }) => {
    await save(page, { country: "Canada", region: "Ontario", postal: "K1A 0B1" });
    await expect(addresses(page)).toHaveCount(1);
    await save(page, { country: "Germany", region: "Berlin", postal: "10115" });
    await expect(addresses(page)).toHaveCount(2);

    await expect(addresses(page).nth(0)).toContainText("(default)");
    await expect(addresses(page).nth(0).getByRole("button", { name: /as default/ })).toHaveCount(0);
    await expect(addresses(page).nth(1)).not.toContainText("(default)");
    await expect(addresses(page).nth(1).getByRole("button", { name: "Set Berlin as default" })).toBeVisible();
  });

  test("Set as default moves the default to exactly one address", async ({ page }) => {
    await save(page, { country: "Canada", region: "Ontario", postal: "K1A 0B1" });
    await expect(addresses(page)).toHaveCount(1);
    await save(page, { country: "Germany", region: "Berlin", postal: "10115" });
    await expect(addresses(page)).toHaveCount(2);
    await save(page, { country: "United States", region: "Texas", postal: "73301" });
    await expect(addresses(page)).toHaveCount(3);

    await page.getByRole("button", { name: "Set Texas as default" }).click();
    await expect(addresses(page).nth(2)).toContainText("(default)");
    await expect(addresses(page).filter({ hasText: "(default)" })).toHaveCount(1);
    await expect(addresses(page).nth(0)).not.toContainText("(default)");
    await expect(addresses(page).nth(0).getByRole("button", { name: "Set Ontario as default" })).toBeVisible();

    await page.getByRole("button", { name: "Set Berlin as default" }).click();
    await expect(addresses(page).nth(1)).toContainText("(default)");
    await expect(addresses(page).filter({ hasText: "(default)" })).toHaveCount(1);
    await expect(addresses(page).nth(2)).not.toContainText("(default)");
  });

  test("the default survives a reload", async ({ page }) => {
    await save(page, { country: "Canada", region: "Ontario", postal: "K1A 0B1" });
    await expect(addresses(page)).toHaveCount(1);
    await save(page, { country: "Germany", region: "Berlin", postal: "10115" });
    await expect(addresses(page)).toHaveCount(2);
    await page.getByRole("button", { name: "Set Berlin as default" }).click();
    await expect(addresses(page).nth(1)).toContainText("(default)");

    await page.reload();
    await expect(addresses(page)).toHaveCount(2);
    await expect(addresses(page).filter({ hasText: "(default)" })).toHaveCount(1);
    await expect(addresses(page).nth(1)).toContainText("(default)");
    await expect(addresses(page).nth(0)).not.toContainText("(default)");
  });

  test("saved addresses survive a reload with the first as default", async ({ page }) => {
    await save(page, { country: "United States", region: "California", postal: "90210" });
    await expect(addresses(page)).toHaveCount(1);
    await page.reload();
    await expect(addresses(page)).toHaveCount(1);
    await expect(addresses(page).first()).toContainText("California, United States 90210 (default)");
  });
});
