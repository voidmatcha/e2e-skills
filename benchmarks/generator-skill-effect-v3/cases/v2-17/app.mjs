import { createServer } from "node:http";

const PORT = __PORT__;
const seed = () => [
  { id: 1, title: "Grocery list", trashed: false },
  { id: 2, title: "Meeting notes", trashed: false },
  { id: 3, title: "Gift ideas", trashed: false },
  { id: 4, title: "Old draft", trashed: true },
];
let notes = seed();

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Notes</title></head>
<body>
  <main>
    <h1>Notes</h1>
    <div role="tablist" aria-label="Views" id="tr-tabs">
      <button type="button" role="tab" id="tr-tab-notes" aria-selected="true">Notes</button>
      <button type="button" role="tab" id="tr-tab-trash" aria-selected="false">Trash (0)</button>
    </div>
    <section id="tr-notes" role="tabpanel" aria-label="Notes view">
      <ul id="tr-notes-list" aria-label="Notes"></ul>
    </section>
    <section id="tr-trash" role="tabpanel" aria-label="Trash view" hidden>
      <button type="button" id="tr-empty">Empty trash</button>
      <ul id="tr-trash-list" aria-label="Trash"></ul>
      <p id="tr-trash-empty" hidden>Trash is empty</p>
    </section>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    let state = [];
    let view = "notes";

    async function api(method, path) {
      const res = await fetch(path, { method });
      return res.ok ? res.json() : null;
    }

    function item(note, actionLabel, action) {
      const li = document.createElement("li");
      li.className = "note";
      const title = document.createElement("span");
      title.textContent = note.title;
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = actionLabel;
      button.setAttribute("aria-label", actionLabel + " " + note.title);
      button.addEventListener("click", () => action(note));
      li.append(title, button);
      return li;
    }

    function render() {
      const active = state.filter((n) => !n.trashed);
      const trashed = state.filter((n) => n.trashed);
      el("tr-tab-trash").textContent = "Trash (" + trashed.length + ")";
      el("tr-tab-notes").setAttribute("aria-selected", String(view === "notes"));
      el("tr-tab-trash").setAttribute("aria-selected", String(view === "trash"));
      el("tr-notes").hidden = view !== "notes";
      el("tr-trash").hidden = view !== "trash";
      el("tr-notes-list").replaceChildren(...active.map((note) => item(note, "Delete", async (n) => {
        await api("POST", "/api/notes/" + n.id + "/trash");
        n.trashed = true;
        render();
      })));
      el("tr-trash-list").replaceChildren(...trashed.map((note) => item(note, "Restore", async (n) => {
        await api("POST", "/api/notes/" + n.id + "/restore");
        n.trashed = false;
        render();
      })));
      el("tr-trash-empty").hidden = trashed.length > 0;
      el("tr-empty").disabled = trashed.length === 0;
    }

    el("tr-tab-notes").addEventListener("click", () => { view = "notes"; render(); });
    el("tr-tab-trash").addEventListener("click", () => { view = "trash"; render(); });
    el("tr-empty").addEventListener("click", async () => {
      if (!confirm("Permanently delete everything in the Trash?")) return;
      await api("POST", "/api/trash/empty");
      state = state.filter((n) => !n.trashed);
      render();
    });

    api("GET", "/api/notes").then((list) => { state = list; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/notes" && req.method === "GET") return json(res, 200, notes);
    const match = url.pathname.match(/^\/api\/notes\/(\d+)\/(trash|restore)$/);
    if (match && req.method === "POST") {
      const note = notes.find((n) => n.id === Number(match[1]));
      if (!note) return json(res, 404, { error: "Not found" });
      note.trashed = match[2] === "trash";
      return json(res, 200, note);
    }
    if (url.pathname === "/api/trash/empty" && req.method === "POST") {
      notes = notes.filter((n) => !n.trashed);
      return json(res, 200, { ok: true });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      notes = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
