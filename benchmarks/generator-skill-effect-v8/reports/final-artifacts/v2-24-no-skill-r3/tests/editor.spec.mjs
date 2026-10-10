import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("autosaves the draft after typing stops and restores it after reload", async ({ page }) => {
  await page.goto("/");

  const title = page.getByLabel("Title");
  const body = page.getByLabel("Body");

  await title.fill("Field notes from the ridge");
  await body.fill("The afternoon light held steady over the valley.");

  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await page.reload();
  await expect(title).toHaveValue("Field notes from the ridge");
  await expect(body).toHaveValue("The afternoon light held steady over the valley.");
});

test("publishing adds the post and clears the draft after reload", async ({ page }) => {
  await page.goto("/");

  const title = page.getByLabel("Title");
  const body = page.getByLabel("Body");

  await title.fill("Launch notes");
  await body.fill("Ship the editor coverage.");
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Publish" }).click();

  await expect(page.getByRole("list", { name: "Published posts" })).toContainText("Launch notes");
  await expect(title).toHaveValue("");
  await expect(body).toHaveValue("");

  await page.reload();
  await expect(page.getByRole("list", { name: "Published posts" })).toContainText("Launch notes");
  await expect(title).toHaveValue("");
  await expect(body).toHaveValue("");
});

test("discarding clears the draft after reload", async ({ page }) => {
  await page.goto("/");

  const title = page.getByLabel("Title");
  const body = page.getByLabel("Body");

  await title.fill("Throwaway title");
  await body.fill("This draft should not survive.");
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Discard draft" }).click();

  await expect(title).toHaveValue("");
  await expect(body).toHaveValue("");

  await page.reload();
  await expect(title).toHaveValue("");
  await expect(body).toHaveValue("");
});
