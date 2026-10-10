import { expect, test } from "@playwright/test";

function headcount(page, members, onLeave) {
  return page.getByText(new RegExp(`^${members} members? \\u00b7 ${onLeave} on leave$`));
}

const memberRow = (page, name) => page.getByRole("row").filter({ hasText: name });

const confirmationRow = (page, firstName) =>
  page.getByRole("row").filter({ hasText: `Remove ${firstName}?` });

test.beforeEach(async ({ page, request }) => {
  const reset = await request.post("/api/reset");
  await expect(reset).toBeOK();
  await page.goto("/");
  await expect(headcount(page, 5, 1)).toBeVisible();
});

test("shows the seeded roster with Linus on leave", async ({ page }) => {
  await expect(page.getByRole("heading", { name: /^Team roster$/ })).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(6);
  await expect(memberRow(page, "Ada Lovelace").getByText("Active")).toBeVisible();
  await expect(memberRow(page, "Grace Hopper").getByText("Active")).toBeVisible();
  await expect(memberRow(page, "Linus Torvalds").getByText("On leave")).toBeVisible();
  await expect(memberRow(page, "Margaret Hamilton").getByText("Active")).toBeVisible();
  await expect(memberRow(page, "Ken Thompson").getByText("Active")).toBeVisible();
});

test("toggles a member leave status and persists it after reload", async ({ page }) => {
  const adaRow = memberRow(page, "Ada Lovelace");
  const patchRequests = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (request.method() === "PATCH" && url.pathname === "/api/members/1") {
      patchRequests.push(request);
    }
  });

  const patchResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      response.request().method() === "PATCH" &&
      url.pathname === "/api/members/1" &&
      response.status() === 200
    );
  });

  await adaRow.getByRole("button", { name: "Toggle leave for Ada Lovelace" }).click();
  await patchResponse;

  expect(patchRequests).toHaveLength(1);
  expect(patchRequests[0].postDataJSON()).toEqual({ onLeave: true });
  await expect(adaRow.getByText("On leave")).toBeVisible();
  await expect(headcount(page, 5, 2)).toBeVisible();

  await page.reload();
  await expect(memberRow(page, "Ada Lovelace").getByText("On leave")).toBeVisible();
  await expect(headcount(page, 5, 2)).toBeVisible();
});

test("cancels removing a member and keeps the roster unchanged", async ({ page }) => {
  await memberRow(page, "Ada Lovelace").getByRole("button", { name: "Remove Ada Lovelace" }).click();
  await expect(confirmationRow(page, "Ada")).toBeVisible();

  await confirmationRow(page, "Ada").getByRole("button", { name: "Cancel removing Ada Lovelace" }).click();

  await expect(confirmationRow(page, "Ada")).not.toBeVisible();
  await expect(memberRow(page, "Ada Lovelace")).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(6);
  await expect(headcount(page, 5, 1)).toBeVisible();
});

test("confirms removing exactly one member and persists it after reload", async ({ page }) => {
  await memberRow(page, "Grace Hopper").getByRole("button", { name: "Remove Grace Hopper" }).click();
  await expect(confirmationRow(page, "Grace")).toBeVisible();

  const deleteRequests = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (request.method() === "DELETE" && url.pathname === "/api/members/2") {
      deleteRequests.push(request);
    }
  });

  const deleteResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      response.request().method() === "DELETE" &&
      url.pathname === "/api/members/2" &&
      response.status() === 200
    );
  });

  await confirmationRow(page, "Grace")
    .getByRole("button", { name: "Confirm removing Grace Hopper" })
    .click();
  await deleteResponse;

  expect(deleteRequests).toHaveLength(1);
  await expect(memberRow(page, "Grace Hopper")).toHaveCount(0);
  await expect(memberRow(page, "Ada Lovelace")).toBeVisible();
  await expect(memberRow(page, "Linus Torvalds")).toBeVisible();
  await expect(memberRow(page, "Margaret Hamilton")).toBeVisible();
  await expect(memberRow(page, "Ken Thompson")).toBeVisible();
  await expect(headcount(page, 4, 1)).toBeVisible();

  await page.reload();
  await expect(memberRow(page, "Grace Hopper")).toHaveCount(0);
  await expect(headcount(page, 4, 1)).toBeVisible();
});
