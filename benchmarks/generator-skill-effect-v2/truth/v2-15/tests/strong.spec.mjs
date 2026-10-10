import { expect, test } from "@playwright/test";

const saved = (page) => page.getByRole("list", { name: "Saved addresses" }).getByRole("listitem");

async function save(page, country, region, postal) {
  await page.getByLabel("Country").selectOption({ label: country });
  await page.getByLabel("Region").selectOption(region);
  await page.getByLabel("Postal code").fill(postal);
  await page.getByRole("button", { name: "Save address" }).click();
}

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("choosing a country fills the regions and clears the previous choice", async ({ page }) => {
  await expect(page.getByLabel("Region")).toBeDisabled();
  await page.getByLabel("Country").selectOption({ label: "United States" });
  await expect(page.getByLabel("Region")).toBeEnabled();
  await page.getByLabel("Region").selectOption("California");
  await page.getByLabel("Country").selectOption({ label: "Germany" });
  await expect(page.getByLabel("Region")).toHaveValue("");
  await expect(page.getByLabel("Region").locator("option")).toHaveText(["Choose a region", "Bavaria", "Berlin", "Hamburg", "Saxony"]);
});

test("postal codes are checked per country", async ({ page }) => {
  await save(page, "Germany", "Berlin", "1234");
  await expect(page.getByRole("alert")).toHaveText("Enter a valid postal code for Germany");
  await expect(saved(page)).toHaveCount(0);
  await page.getByLabel("Postal code").fill("10115");
  await page.getByRole("button", { name: "Save address" }).click();
  await expect(saved(page)).toHaveText([/Berlin, Germany 10115 \(default\)/]);
  await save(page, "Canada", "Ontario", "12345");
  await expect(page.getByRole("alert")).toHaveText("Enter a valid postal code for Canada");
  await page.getByLabel("Postal code").fill("M5V 2T6");
  await page.getByRole("button", { name: "Save address" }).click();
  await expect(saved(page)).toHaveCount(2);
});

test("exactly one default, and it survives a reload", async ({ page }) => {
  await save(page, "United States", "Texas", "73301");
  await save(page, "United States", "New York", "10001");
  await expect(saved(page).filter({ hasText: "(default)" })).toHaveText([/Texas/]);
  await page.getByRole("button", { name: "Set New York as default" }).click();
  await expect(saved(page).filter({ hasText: "(default)" })).toHaveText([/New York/]);
  await expect(page.getByRole("button", { name: "Set Texas as default" })).toBeVisible();
  await page.reload();
  await expect(saved(page).filter({ hasText: "(default)" })).toHaveText([/New York/]);
  await expect(saved(page).filter({ hasText: "(default)" })).toHaveCount(1);
});
