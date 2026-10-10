import { expect } from "@playwright/test";

export class NotesPage {
  constructor(page) {
    this.page = page;
    this.count = page.locator("#nt-count");
    this.titleInput = page.getByLabel("Title", { exact: true });
    this.addButton = page.getByRole("button", { name: "Add", exact: true });
    this.items = page.getByRole("list", { name: "Notes" }).getByRole("listitem");
    this.titles = this.items.locator(".title");
  }

  // Every test starts from an empty server via the reset seam.
  async reset() {
    const res = await this.page.request.post("/api/reset");
    expect(res.ok()).toBeTruthy();
  }

  // Seeds notes through the app's own API, in the given order.
  async seed(titles) {
    for (const title of titles) {
      const res = await this.page.request.post("/api/notes", { data: { title } });
      expect(res.status()).toBe(201);
    }
  }

  // Waits for the initial list fetch so a fast first action cannot be overwritten by it.
  async open() {
    const loaded = this.page.waitForResponse(
      (r) => r.url().endsWith("/api/notes") && r.request().method() === "GET",
    );
    await this.page.goto("/");
    await loaded;
  }

  async reload() {
    const loaded = this.page.waitForResponse(
      (r) => r.url().endsWith("/api/notes") && r.request().method() === "GET",
    );
    await this.page.reload();
    await loaded;
  }

  async add(title) {
    await this.titleInput.fill(title);
    await this.addButton.click();
  }

  editButton(title) {
    return this.page.getByRole("button", { name: `Edit ${title}`, exact: true });
  }

  deleteButton(title) {
    return this.page.getByRole("button", { name: `Delete ${title}`, exact: true });
  }

  editField(title) {
    return this.page.getByRole("textbox", { name: `New title for ${title}`, exact: true });
  }

  saveButton(title) {
    return this.page.getByRole("button", { name: `Save ${title}`, exact: true });
  }
}
