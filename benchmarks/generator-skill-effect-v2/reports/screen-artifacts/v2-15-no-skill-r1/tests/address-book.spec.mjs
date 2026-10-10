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

test("choosing a country fills its regions", async ({ page }) => {
  const region = page.getByLabel("Region");
  await expect(region).toBeDisabled();
  await page.getByLabel("Country").selectOption({ label: "Canada" });
  await expect(region).toBeEnabled();
  await expect(region.locator("option")).toHaveText(["Choose a region", "Alberta", "British Columbia", "Ontario", "Quebec"]);
  await page.getByLabel("Country").selectOption({ label: "Germany" });
  await expect(region.locator("option")).toHaveText(["Choose a region", "Bavaria", "Berlin", "Hamburg", "Saxony"]);
});

test("changing country clears the chosen region", async ({ page }) => {
  const region = page.getByLabel("Region");
  await page.getByLabel("Country").selectOption({ label: "Canada" });
  await region.selectOption("Ontario");
  await expect(region).toHaveValue("Ontario");
  await page.getByLabel("Country").selectOption({ label: "United States" });
  await expect(region).toHaveValue("");
  await expect(region.locator("option")).toHaveText(["Choose a region", "California", "New York", "Texas", "Washington"]);
});

for (const [country, region, bad, good] of [
  ["Canada", "Ontario", "12345", "K1A 0B1"],
  ["Canada", "Ontario", "K1A0B1", "K1A 0B1"],
  ["Germany", "Berlin", "1234", "10115"],
  ["Germany", "Berlin", "123456", "10115"],
  ["United States", "Texas", "ABCDE", "73301"],
  ["United States", "Texas", "1234", "73301"],
]) {
  test(`rejects postal code "${bad}" for ${country} without saving, accepts "${good}"`, async ({ page }) => {
    await save(page, country, region, bad);
    await expect(page.getByRole("alert")).toHaveText(`Enter a valid postal code for ${country}`);
    await expect(items(page)).toHaveCount(0);
    expect(await (await page.request.get("/api/addresses")).json()).toEqual([]);

    await page.getByLabel("Postal code").fill(good);
    await page.getByRole("button", { name: "Save address" }).click();
    await expect(items(page)).toHaveCount(1);
    await expect(page.getByRole("alert")).toHaveText("");
  });
}

test("saved addresses are listed and the form resets", async ({ page }) => {
  await save(page, "Canada", "Quebec", "H2X 1Y4");
  await expect(items(page)).toHaveText(["Quebec, Canada H2X 1Y4 (default)"]);
  await expect(page.getByLabel("Country")).toHaveValue("");
  await expect(page.getByLabel("Postal code")).toHaveValue("");
  await expect(page.getByLabel("Region")).toBeDisabled();
});

test("first saved address is the default; set as default moves it", async ({ page }) => {
  await save(page, "Germany", "Berlin", "10115");
  await expect(items(page)).toHaveCount(1);
  await save(page, "United States", "Texas", "73301");
  await expect(items(page)).toHaveCount(2);
  await save(page, "Canada", "Alberta", "T5J 2R7");
  await expect(items(page)).toHaveCount(3);

  const defaults = page.getByRole("listitem").filter({ hasText: "(default)" });
  await expect(defaults).toHaveCount(1);
  await expect(defaults).toContainText("Berlin");
  await expect(page.getByRole("button", { name: /^Set .* as default$/ })).toHaveCount(2);

  await page.getByRole("button", { name: "Set Texas as default" }).click();
  await expect(defaults).toHaveCount(1);
  await expect(defaults).toContainText("Texas");
  await expect(items(page).filter({ hasText: "Berlin" })).not.toContainText("(default)");
  await expect(page.getByRole("button", { name: "Set Berlin as default" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Set Texas as default" })).toHaveCount(0);

  await page.reload();
  await expect(items(page)).toHaveCount(3);
  await expect(defaults).toHaveCount(1);
  await expect(defaults).toContainText("Texas");
});
