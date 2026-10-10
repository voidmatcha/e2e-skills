import { expect, test } from "@playwright/test";

test("claims the chosen product once and persists inventory", async ({ page }) => {
  await page.goto("/");
  const lamp = page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "Claim Lamp" }) });
  const desk = page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "Claim Desk" }) });
  await expect(page.getByRole("status")).toHaveText("Claimed: 0");
  await expect(lamp).toContainText("Lamp: 3 left");
  await expect(desk).toContainText("Desk: 3 left");

  await page.getByRole("button", { name: "Claim Lamp" }).click();
  await expect(page.getByRole("status")).toHaveText("Claimed: 1");
  await expect(lamp).toContainText("Lamp: 2 left");
  await expect(desk).toContainText("Desk: 3 left");

  await page.getByRole("button", { name: "Claim Desk" }).click();
  await expect(page.getByRole("status")).toHaveText("Claimed: 2");
  await expect(lamp).toContainText("Lamp: 2 left");
  await expect(desk).toContainText("Desk: 2 left");

  await page.reload();
  await expect(page.getByRole("status")).toHaveText("Claimed: 2");
  await expect(lamp).toContainText("Lamp: 2 left");
  await expect(desk).toContainText("Desk: 2 left");

  await page.getByRole("button", { name: "Claim Lamp" }).click();
  await expect(page.getByRole("status")).toHaveText("Claimed: 3");
  await expect(lamp).toContainText("Lamp: 1 left");
  await expect(desk).toContainText("Desk: 2 left");
});
