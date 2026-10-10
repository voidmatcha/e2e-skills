import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

async function enterAddress(page, { name = "Ada Lovelace", street = "12 Algorithm Ave", city = "London" } = {}) {
  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Street").fill(street);
  await page.getByLabel("City").fill(city);
  await page.getByRole("button", { name: "Next" }).click();
}

async function chooseMethod(page, method) {
  await page.getByLabel(method).check();
  await page.getByRole("button", { name: "Next" }).click();
}

test("completes checkout and keeps the order after reload", async ({ page }) => {
  await page.goto("/");

  await enterAddress(page, { city: "Portland" });
  await chooseMethod(page, "Express ($15.00)");

  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Items" }).locator("li")).toHaveText([
    "Desk lamp — $40.00",
    "Notebook — $8.00",
  ]);
  await expect(page.locator("#co-shipping-line")).toHaveText("Shipping (Express): $15.00");
  await expect(page.locator("#co-total")).toHaveText("Total: $63.00");

  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.getByRole("status")).toHaveText("Order #1001 confirmed");
  await expect(page.getByRole("list", { name: "Your orders" })).toContainText("Order #1001 — $63.00 — Portland");

  await page.reload();
  await expect(page.getByRole("list", { name: "Your orders" })).toContainText("Order #1001 — $63.00 — Portland");
});

test("keeps the shipping address when going back", async ({ page }) => {
  await page.goto("/");

  await enterAddress(page, { name: "Grace Hopper", street: "1 Compiler Way", city: "Arlington" });
  await page.getByRole("button", { name: "Back" }).click();

  await expect(page.getByLabel("Full name")).toHaveValue("Grace Hopper");
  await expect(page.getByLabel("Street")).toHaveValue("1 Compiler Way");
  await expect(page.getByLabel("City")).toHaveValue("Arlington");
});

test("shows a decline and does not create an order", async ({ page }) => {
  await page.goto("/");

  await enterAddress(page, { city: "Failville" });
  await chooseMethod(page, "Standard ($5.00)");

  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveText("Payment declined");
  await expect(page.getByRole("list", { name: "Your orders" }).locator("li")).toHaveCount(0);
});
