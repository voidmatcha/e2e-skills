import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("updates regions for the selected country and clears the previous region", async ({ page }) => {
  await page.goto("/");

  const country = page.getByLabel("Country");
  const region = page.getByLabel("Region");

  await country.selectOption("CA");
  await expect(region.getByRole("option")).toHaveText([
    "Choose a region",
    "Alberta",
    "British Columbia",
    "Ontario",
    "Quebec",
  ]);

  await region.selectOption("Ontario");
  await country.selectOption("DE");

  await expect(region).toHaveValue("");
  await expect(region.getByRole("option")).toHaveText([
    "Choose a region",
    "Bavaria",
    "Berlin",
    "Hamburg",
    "Saxony",
  ]);
});

test("rejects postal codes that do not match the selected country", async ({ page, request }) => {
  await page.goto("/");

  const country = page.getByLabel("Country");
  const region = page.getByLabel("Region");
  const postalCode = page.getByLabel("Postal code");
  const saveAddress = page.getByRole("button", { name: "Save address", exact: true });

  const invalidAddresses = [
    { country: "CA", countryName: "Canada", region: "Ontario", postal: "12345" },
    { country: "DE", countryName: "Germany", region: "Berlin", postal: "A1A 1A1" },
    { country: "US", countryName: "United States", region: "Texas", postal: "ABCDE" },
  ];

  for (const invalidAddress of invalidAddresses) {
    await country.selectOption(invalidAddress.country);
    await region.selectOption(invalidAddress.region);
    await postalCode.fill(invalidAddress.postal);

    const saveRequest = page.waitForRequest(
      (request) =>
        request.method() === "POST" &&
        new URL(request.url()).pathname === "/api/addresses",
    );
    await saveAddress.click();
    await saveRequest;

    await expect(page.getByRole("alert")).toHaveText(
      `Enter a valid postal code for ${invalidAddress.countryName}`,
    );
  }

  const storedAddresses = await request.get("/api/addresses");
  await expect(storedAddresses).toBeOK();
  await expect(await storedAddresses.json()).toEqual([]);
});

test("marks the first saved address as default and keeps one default after changing it", async ({ page }) => {
  await page.goto("/");

  const country = page.getByLabel("Country");
  const region = page.getByLabel("Region");
  const postalCode = page.getByLabel("Postal code");
  const saveAddress = page.getByRole("button", { name: "Save address", exact: true });
  const savedAddresses = page.getByRole("list", { name: "Saved addresses", exact: true });

  await country.selectOption("CA");
  await region.selectOption("Ontario");
  await postalCode.fill("A1A 1A1");

  const firstSaveRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/addresses",
  );
  await saveAddress.click();
  await firstSaveRequest;

  const firstAddress = savedAddresses.getByRole("listitem").filter({
    hasText: "Ontario, Canada A1A 1A1",
  });
  await expect(firstAddress).toContainText("(default)");

  await country.selectOption("DE");
  await region.selectOption("Berlin");
  await postalCode.fill("10115");

  const secondSaveRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/addresses",
  );
  await saveAddress.click();
  await secondSaveRequest;

  const secondAddress = savedAddresses.getByRole("listitem").filter({
    hasText: "Berlin, Germany 10115",
  });
  await expect(firstAddress).toContainText("(default)");
  await expect(secondAddress).not.toContainText("(default)");

  const defaultRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      /\/api\/addresses\/\d+\/default$/.test(new URL(request.url()).pathname),
  );
  await secondAddress.getByRole("button", { name: "Set Berlin as default" }).click();
  await defaultRequest;

  await expect(savedAddresses.getByRole("listitem").filter({ hasText: "(default)" })).toHaveCount(1);
  await expect(firstAddress).not.toContainText("(default)");
  await expect(secondAddress).toContainText("(default)");

  await page.reload();
  const reloadedAddresses = page.getByRole("list", { name: "Saved addresses", exact: true });
  await expect(reloadedAddresses.getByRole("listitem").filter({ hasText: "(default)" })).toHaveCount(1);
  await expect(
    reloadedAddresses.getByRole("listitem").filter({ hasText: "Berlin, Germany 10115 (default)" }),
  ).toHaveCount(1);
});
