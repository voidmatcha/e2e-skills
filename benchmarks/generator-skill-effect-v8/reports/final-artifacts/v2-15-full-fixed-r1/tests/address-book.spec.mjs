import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

async function chooseAddress(page, { country, region, postal }) {
  await page.getByLabel("Country").selectOption(country);
  await page.getByLabel("Region").selectOption(region);
  await page.getByLabel("Postal code").fill(postal);
}

async function saveAddress(page, address) {
  await chooseAddress(page, address);

  const saveRequest = page.waitForRequest((request) => {
    return request.method() === "POST" && new URL(request.url()).pathname === "/api/addresses";
  });
  await page.getByRole("button", { name: "Save address", exact: true }).click();
  return saveRequest;
}

test("updates regions for the chosen country and clears the previous region", async ({ page }) => {
  const country = page.getByLabel("Country");
  const region = page.getByLabel("Region");

  await country.selectOption("CA");
  await region.selectOption("Ontario");
  await expect(region).toHaveValue("Ontario");

  await country.selectOption("DE");

  await expect(region).toHaveValue("");
  await region.selectOption("Berlin");
  await expect(region).toHaveValue("Berlin");
  await expect(region).not.toContainText("Ontario");
});

test("shows country-specific postal code errors without saving an address", async ({ page }) => {
  const savedAddresses = page.getByRole("list", { name: "Saved addresses", exact: true });
  const invalidPostalCases = [
    { country: "CA", region: "Ontario", postal: "12345", message: "Enter a valid postal code for Canada" },
    { country: "DE", region: "Berlin", postal: "A1A 1A1", message: "Enter a valid postal code for Germany" },
    { country: "US", region: "Texas", postal: "ABCDE", message: "Enter a valid postal code for United States" },
  ];

  for (const address of invalidPostalCases) {
    const response = page.waitForResponse((response) => {
      return response.request().method() === "POST" && new URL(response.url()).pathname === "/api/addresses";
    });

    await chooseAddress(page, address);
    await page.getByRole("button", { name: "Save address", exact: true }).click();

    await expect(page.getByRole("alert")).toHaveText(address.message);
    expect((await response).status()).toBe(400);
    await page.reload();
    await expect(savedAddresses).toBeEmpty();
  }
});

test("keeps exactly one default address and preserves it after reload", async ({ page }) => {
  const savedAddresses = page.getByRole("list", { name: "Saved addresses", exact: true });

  const canadaSave = await saveAddress(page, { country: "CA", region: "Alberta", postal: "A1A 1A1" });
  expect(JSON.parse(canadaSave.postData())).toEqual({ country: "CA", region: "Alberta", postal: "A1A 1A1" });
  const canadaAddress = savedAddresses.getByRole("listitem").filter({ hasText: "Alberta, Canada A1A 1A1" });
  await expect(canadaAddress).toContainText("(default)");

  const germanySave = await saveAddress(page, { country: "DE", region: "Berlin", postal: "10115" });
  expect(JSON.parse(germanySave.postData())).toEqual({ country: "DE", region: "Berlin", postal: "10115" });
  const germanyAddress = savedAddresses.getByRole("listitem").filter({ hasText: "Berlin, Germany 10115" });
  await expect(germanyAddress).not.toContainText("(default)");

  const defaultRequest = page.waitForRequest((request) => {
    return request.method() === "POST" && /\/api\/addresses\/\d+\/default$/.test(new URL(request.url()).pathname);
  });
  await page.getByRole("button", { name: "Set Berlin as default", exact: true }).click();
  await defaultRequest;

  await expect(germanyAddress).toContainText("(default)");
  await expect(canadaAddress).not.toContainText("(default)");

  await page.reload();
  await expect(savedAddresses.getByRole("listitem").filter({ hasText: "Berlin, Germany 10115" })).toContainText("(default)");
  await expect(savedAddresses.getByRole("listitem").filter({ hasText: "Alberta, Canada A1A 1A1" })).not.toContainText("(default)");
});
