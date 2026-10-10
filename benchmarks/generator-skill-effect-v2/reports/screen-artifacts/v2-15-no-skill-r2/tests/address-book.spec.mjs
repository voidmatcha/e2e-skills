import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
});

async function saveAddress(page, { country, region, postal }) {
  await page.getByLabel("Country").selectOption({ label: country });
  await page.getByLabel("Region").selectOption({ label: region });
  await page.getByLabel("Postal code").fill(postal);
  await page.getByRole("button", { name: "Save address" }).click();
}

const list = (page) => page.getByRole("list", { name: "Saved addresses" });
const rows = (page) => list(page).getByRole("listitem");

test.describe("country and region", () => {
  test("region is disabled until a country is chosen", async ({ page }) => {
    await expect(page.getByLabel("Region")).toBeDisabled();
  });

  for (const [country, regions] of [
    ["Canada", ["Alberta", "British Columbia", "Ontario", "Quebec"]],
    ["Germany", ["Bavaria", "Berlin", "Hamburg", "Saxony"]],
    ["United States", ["California", "New York", "Texas", "Washington"]],
  ]) {
    test(`choosing ${country} lists its regions`, async ({ page }) => {
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
  });

  test("resetting to no country disables and empties the region list", async ({ page }) => {
    await page.getByLabel("Country").selectOption({ label: "Canada" });
    await page.getByLabel("Country").selectOption({ label: "Choose a country" });
    await expect(page.getByLabel("Region")).toBeDisabled();
    await expect(page.getByLabel("Region")).toHaveValue("");
    await expect(page.getByLabel("Region").locator("option")).toHaveText(["Choose a region"]);
  });
});

test.describe("postal code validation", () => {
  const invalid = [
    ["Canada", "Ontario", "12345"],
    ["Canada", "Ontario", "K1A0B1"],
    ["Canada", "Ontario", ""],
    ["Germany", "Berlin", "1234"],
    ["Germany", "Berlin", "123456"],
    ["Germany", "Berlin", "1234a"],
    ["United States", "Texas", "1234"],
    ["United States", "Texas", "123456"],
    ["United States", "Texas", "K1A 0B1"],
  ];
  for (const [country, region, postal] of invalid) {
    test(`rejects "${postal}" for ${country}`, async ({ page }) => {
      await saveAddress(page, { country, region, postal });
      await expect(page.getByRole("alert")).toHaveText(`Enter a valid postal code for ${country}`);
      await expect(rows(page)).toHaveCount(0);
      expect(await (await page.request.get("/api/addresses")).json()).toEqual([]);
    });
  }

  const valid = [
    ["Canada", "Ontario", "K1A 0B1"],
    ["Germany", "Berlin", "10115"],
    ["United States", "Texas", "73301"],
  ];
  for (const [country, region, postal] of valid) {
    test(`accepts "${postal}" for ${country}`, async ({ page }) => {
      await saveAddress(page, { country, region, postal });
      await expect(rows(page)).toHaveCount(1);
      await expect(rows(page).first()).toContainText(`${region}, ${country} ${postal}`);
      await expect(page.getByRole("alert")).toHaveText("");
    });
  }

  test("a corrected postal code saves and clears the error", async ({ page }) => {
    await saveAddress(page, { country: "Germany", region: "Berlin", postal: "abc" });
    await expect(page.getByRole("alert")).toHaveText("Enter a valid postal code for Germany");
    await page.getByLabel("Postal code").fill("10115");
    await page.getByRole("button", { name: "Save address" }).click();
    await expect(page.getByRole("alert")).toHaveText("");
    await expect(rows(page)).toHaveCount(1);
  });

  test("the form is cleared after a successful save", async ({ page }) => {
    await saveAddress(page, { country: "Germany", region: "Berlin", postal: "10115" });
    await expect(rows(page)).toHaveCount(1);
    await expect(page.getByLabel("Country")).toHaveValue("");
    await expect(page.getByLabel("Region")).toHaveValue("");
    await expect(page.getByLabel("Postal code")).toHaveValue("");
  });
});

test.describe("default address", () => {
  test("the first saved address is the default, later ones are not", async ({ page }) => {
    await saveAddress(page, { country: "Canada", region: "Ontario", postal: "K1A 0B1" });
    await saveAddress(page, { country: "Germany", region: "Berlin", postal: "10115" });
    await expect(rows(page)).toHaveCount(2);

    await expect(rows(page).nth(0)).toContainText("(default)");
    await expect(rows(page).nth(0).getByRole("button", { name: "Set Ontario as default" })).toHaveCount(0);
    await expect(rows(page).nth(1)).not.toContainText("(default)");
    await expect(rows(page).nth(1).getByRole("button", { name: "Set Berlin as default" })).toBeVisible();
  });

  test("Set as default moves the default and leaves exactly one", async ({ page }) => {
    await saveAddress(page, { country: "Canada", region: "Ontario", postal: "K1A 0B1" });
    await saveAddress(page, { country: "Germany", region: "Berlin", postal: "10115" });
    await saveAddress(page, { country: "United States", region: "Texas", postal: "73301" });
    await expect(rows(page)).toHaveCount(3);

    await page.getByRole("button", { name: "Set Berlin as default" }).click();
    await expect(rows(page).nth(1)).toContainText("(default)");
    await expect(rows(page).nth(0)).not.toContainText("(default)");
    await expect(rows(page).nth(2)).not.toContainText("(default)");
    await expect(list(page).getByText("(default)")).toHaveCount(1);

    await page.getByRole("button", { name: "Set Texas as default" }).click();
    await expect(rows(page).nth(2)).toContainText("(default)");
    await expect(list(page).getByText("(default)")).toHaveCount(1);
    await expect(page.getByRole("button", { name: /as default/ })).toHaveCount(2);
  });

  test("the default survives a reload", async ({ page }) => {
    await saveAddress(page, { country: "Canada", region: "Ontario", postal: "K1A 0B1" });
    await saveAddress(page, { country: "Germany", region: "Berlin", postal: "10115" });
    await page.getByRole("button", { name: "Set Berlin as default" }).click();
    await expect(rows(page).nth(1)).toContainText("(default)");

    await page.reload();
    await expect(rows(page)).toHaveCount(2);
    await expect(rows(page).nth(1)).toContainText("(default)");
    await expect(rows(page).nth(0)).not.toContainText("(default)");
    await expect(list(page).getByText("(default)")).toHaveCount(1);
  });

  test("a rejected save does not take the default or change the existing one", async ({ page }) => {
    await saveAddress(page, { country: "Canada", region: "Ontario", postal: "K1A 0B1" });
    await saveAddress(page, { country: "Germany", region: "Berlin", postal: "bad" });
    await expect(page.getByRole("alert")).toHaveText("Enter a valid postal code for Germany");
    await expect(rows(page)).toHaveCount(1);
    await expect(rows(page).first()).toContainText("(default)");
  });
});
