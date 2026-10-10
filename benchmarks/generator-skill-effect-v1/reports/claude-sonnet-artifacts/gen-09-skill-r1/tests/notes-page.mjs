export class NotesPage {
  constructor(page) {
    this.page = page;
    this.heading = page.getByRole("heading", { name: "Notes" });
    this.counter = page.locator("#nt-count");
    this.titleInput = page.getByRole("textbox", { name: "Title", exact: true });
    this.addButton = page.getByRole("button", { name: "Add", exact: true });
    this.list = page.getByRole("list", { name: "Notes" });
    // Title spans are the only element carrying just the note title (rows also hold button text).
    this.titles = this.list.locator(".title");
  }

  async goto() {
    await this.page.goto("/");
    await this.heading.waitFor();
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

  saveButton(title) {
    return this.page.getByRole("button", { name: `Save ${title}`, exact: true });
  }

  editField(title) {
    return this.page.getByRole("textbox", { name: `New title for ${title}`, exact: true });
  }

  // Each test starts from an empty server; seeding goes through the API, not the UI.
  async reset() {
    const res = await this.page.request.post("/api/reset");
    if (!res.ok()) throw new Error(`reset failed: ${res.status()}`);
  }

  async seed(titles) {
    for (const title of titles) {
      const res = await this.page.request.post("/api/notes", { data: { title } });
      if (!res.ok()) throw new Error(`seed failed for ${title}: ${res.status()}`);
    }
  }
}
