import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
});

async function save(page, { country, region, postal }) {
  await page.getByLabel("Country").selectOption({ label: country });
  await page.getByLabel("Region").selectOption({ label: region });
  await page.getByLabel("Postal code").fill(postal);
  await page.getByRole("button", { name: "Save address" }).click();
}

const items = (page) => page.getByRole("list", { name: "Saved addresses" }).getByRole("listitem");

test("region list follows the chosen country", async ({ page }) => {
  const region = page.getByLabel("Region");
  await expect(region).toBeDisabled();

  await page.getByLabel("Country").selectOption({ label: "Canada" });
  await expect(region).toBeEnabled();
  await expect(region.getByRole("option")).toHaveText(["Choose a region", "Alberta", "British Columbia", "Ontario", "Quebec"]);

  await page.getByLabel("Country").selectOption({ label: "Germany" });
  await expect(region.getByRole("option")).toHaveText(["Choose a region", "Bavaria", "Berlin", "Hamburg", "Saxony"]);
});

test("changing country clears the chosen region", async ({ page }) => {
  await page.getByLabel("Country").selectOption({ label: "United States" });
  await page.getByLabel("Region").selectOption({ label: "Texas" });
  await expect(page.getByLabel("Region")).toHaveValue("Texas");

  await page.getByLabel("Country").selectOption({ label: "Canada" });
  await expect(page.getByLabel("Region")).toHaveValue("");

  await page.getByLabel("Country").selectOption({ label: "United States" });
  await expect(page.getByLabel("Region")).toHaveValue("");
});

for (const [country, bad, good] of [
  ["Canada", ["12345", "A1A1A1", "A1A 1A"], "K1A 0B1"],
  ["Germany", ["1234", "123456", "ABCDE"], "10115"],
  ["United States", ["1234", "123456", "12345-6789"], "90210"],
]) {
  test(`postal code validation for ${country}`, async ({ page }) => {
    const region = { Canada: "Ontario", Germany: "Berlin", "United States": "California" }[country];
    for (const postal of bad) {
      await save(page, { country, region, postal });
      await expect(page.getByRole("alert")).toHaveText(`Enter a valid postal code for ${country}`);
      await expect(items(page)).toHaveCount(0);
    }
    await save(page, { country, region, postal: good });
    await expect(items(page)).toHaveCount(1);
    await expect(page.getByRole("alert")).toHaveText("");
  });
}

test("a five digit code valid for Germany is rejected for Canada", async ({ page }) => {
  await save(page, { country: "Canada", region: "Alberta", postal: "10115" });
  await expect(page.getByRole("alert")).toHaveText("Enter a valid postal code for Canada");
});

test("first saved address is the default and the form resets", async ({ page }) => {
  await save(page, { country: "Germany", region: "Berlin", postal: "10115" });
  await expect(items(page)).toHaveCount(1);
  await expect(items(page).first()).toContainText("Berlin, Germany 10115 (default)");
  await expect(page.getByLabel("Country")).toHaveValue("");
  await expect(page.getByLabel("Region")).toBeDisabled();

  await save(page, { country: "Canada", region: "Ontario", postal: "K1A 0B1" });
  await expect(items(page)).toHaveCount(2);
  await expect(items(page).nth(1)).not.toContainText("(default)");
});

test("Set as default moves the default and survives reload", async ({ page }) => {
  await save(page, { country: "Germany", region: "Berlin", postal: "10115" });
  await save(page, { country: "Canada", region: "Ontario", postal: "K1A 0B1" });
  await save(page, { country: "United States", region: "Texas", postal: "73301" });
  await expect(items(page)).toHaveCount(3);

  const defaults = page.getByRole("listitem").filter({ hasText: "(default)" });
  await expect(defaults).toHaveCount(1);
  await expect(defaults).toContainText("Berlin");

  await page.getByRole("button", { name: "Set Texas as default" }).click();
  await expect(defaults).toHaveCount(1);
  await expect(defaults).toContainText("Texas, United States 73301");
  await expect(page.getByRole("button", { name: "Set Texas as default" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Set Berlin as default" })).toBeVisible();

  await page.reload();
  await expect(items(page)).toHaveCount(3);
  await expect(defaults).toHaveCount(1);
  await expect(defaults).toContainText("Texas");
});
