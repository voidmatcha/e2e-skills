import { expect, test } from "@playwright/test";

const countries = {
  Canada: {
    region: "Ontario",
    postal: "K1A 0B1",
    badPostal: "12345",
    regions: ["Choose a region", "Alberta", "British Columbia", "Ontario", "Quebec"],
  },
  Germany: {
    region: "Berlin",
    postal: "10115",
    badPostal: "abc",
    regions: ["Choose a region", "Bavaria", "Berlin", "Hamburg", "Saxony"],
  },
  "United States": {
    region: "Texas",
    postal: "73301",
    badPostal: "A1A 1A1",
    regions: ["Choose a region", "California", "New York", "Texas", "Washington"],
  },
};

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("updates regions for the selected country and clears the previous region", async ({ page }) => {
  const country = page.getByLabel("Country");
  const region = page.getByLabel("Region");

  await country.selectOption({ label: "Canada" });
  await expect(region).toBeEnabled();
  await expect(region.getByRole("option")).toHaveText(countries.Canada.regions);
  await region.selectOption({ label: "Ontario" });
  await expect(region).toHaveValue("Ontario");

  await country.selectOption({ label: "Germany" });
  await expect(region.getByRole("option")).toHaveText(countries.Germany.regions);
  await expect(region).toHaveValue("");
});

for (const [countryName, countryData] of Object.entries(countries)) {
  test(`shows a country-specific postal code error for ${countryName}`, async ({ page }) => {
    const savedAddresses = page.getByRole("list", { name: "Saved addresses", exact: true });

    await page.getByLabel("Country").selectOption({ label: countryName });
    await page.getByLabel("Region").selectOption({ label: countryData.region });
    await page.getByLabel("Postal code").fill(countryData.badPostal);

    const saveRequest = page.waitForRequest((request) => {
      return request.method() === "POST" && request.url().endsWith("/api/addresses");
    });
    const saveResponse = page.waitForResponse((response) => {
      return response.request().method() === "POST" && response.url().endsWith("/api/addresses");
    });
    await page.getByRole("button", { name: "Save address", exact: true }).click();
    await saveRequest;
    expect((await saveResponse).status()).toBe(400);

    await expect(page.getByRole("alert")).toHaveText(`Enter a valid postal code for ${countryName}`);
    await page.reload();
    await expect.poll(async () => {
      const addressesResponse = await page.request.get("/api/addresses");
      return addressesResponse.json();
    }).toEqual([]);
    await expect(savedAddresses.getByRole("listitem")).toHaveCount(0);
  });
}

test("lists saved addresses and marks the first saved address as the default", async ({ page }) => {
  const savedAddresses = page.getByRole("list", { name: "Saved addresses", exact: true });

  await saveAddress(page, "Germany");

  await expect(savedAddresses.getByRole("listitem")).toHaveText("Berlin, Germany 10115 (default)");
});

test("sets exactly one default address and keeps it after reload", async ({ page }) => {
  const savedAddresses = page.getByRole("list", { name: "Saved addresses", exact: true });

  await saveAddress(page, "Germany");
  await saveAddress(page, "United States");

  const defaultRequest = page.waitForRequest((request) => {
    return request.method() === "POST" && /\/api\/addresses\/\d+\/default$/.test(request.url());
  });
  await page.getByRole("button", { name: "Set Texas as default", exact: true }).click();
  await defaultRequest;

  await expect(savedAddresses.getByRole("listitem").filter({ hasText: "(default)" })).toHaveCount(1);
  await expect(savedAddresses.getByRole("listitem").filter({ hasText: "Berlin" })).toContainText("Berlin, Germany 10115");
  await expect(savedAddresses.getByRole("listitem").filter({ hasText: "Texas" })).toContainText(
    "Texas, United States 73301 (default)",
  );

  await page.reload();
  await expect(savedAddresses.getByRole("listitem").filter({ hasText: "(default)" })).toHaveCount(1);
  await expect(savedAddresses.getByRole("listitem").filter({ hasText: "Texas" })).toContainText(
    "Texas, United States 73301 (default)",
  );
});

async function saveAddress(page, countryName) {
  const countryData = countries[countryName];

  await page.getByLabel("Country").selectOption({ label: countryName });
  await page.getByLabel("Region").selectOption({ label: countryData.region });
  await page.getByLabel("Postal code").fill(countryData.postal);

  const saveRequest = page.waitForRequest((request) => {
    if (request.method() !== "POST" || !request.url().endsWith("/api/addresses")) return false;
    const payload = request.postDataJSON();
    return payload.region === countryData.region && payload.postal === countryData.postal;
  });
  await page.getByRole("button", { name: "Save address", exact: true }).click();
  await saveRequest;
}
