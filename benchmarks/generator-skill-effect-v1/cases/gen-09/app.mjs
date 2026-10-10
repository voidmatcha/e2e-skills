import { createServer } from "node:http";

const PORT = __PORT__;
let notes = [];
let nextId = 1;

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));
const readJson = async (req) => {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  return raw ? JSON.parse(raw) : {};
};

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Notes</title></head>
<body>
  <main>
    <h1>Notes</h1>
    <p id="nt-count" aria-live="polite">0 notes</p>
    <form id="nt-form">
      <label for="nt-title">Title</label>
      <input id="nt-title" name="title" autocomplete="off">
      <button type="submit">Add</button>
    </form>
    <ul id="nt-list" aria-label="Notes"></ul>
  </main>
  <script>
    const form = document.getElementById("nt-form");
    const titleEl = document.getElementById("nt-title");
    const listEl = document.getElementById("nt-list");
    const countEl = document.getElementById("nt-count");
    let state = [];
    let editing = null;

    const byTitle = (a, b) => a.title.localeCompare(b.title, "en", { sensitivity: "base" });
    const sorted = (list) => [...list].sort(byTitle);
    const label = (n) => (n === 1 ? "1 note" : n + " notes");

    async function api(method, path, body) {
      const res = await fetch(path, {
        method,
        headers: { "content-type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      return res.ok ? res.json() : null;
    }

    function row(note) {
      const li = document.createElement("li");
      li.className = "note";
      if (editing === note.id) {
        const input = document.createElement("input");
        input.value = note.title;
        input.setAttribute("aria-label", "New title for " + note.title);
        const save = document.createElement("button");
        save.type = "button";
        save.textContent = "Save";
        save.setAttribute("aria-label", "Save " + note.title);
        save.addEventListener("click", async () => {
          const title = input.value;
          await api("PATCH", "/api/notes/" + note.id, { title });
          const target = state.find((n) => n.id === note.id);
          target.title = title;
          editing = null;
          render();
        });
        li.append(input, save);
        return li;
      }
      const title = document.createElement("span");
      title.className = "title";
      title.textContent = note.title;
      const edit = document.createElement("button");
      edit.type = "button";
      edit.textContent = "Edit";
      edit.setAttribute("aria-label", "Edit " + note.title);
      edit.addEventListener("click", () => {
        editing = note.id;
        render();
      });
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Delete";
      remove.setAttribute("aria-label", "Delete " + note.title);
      remove.addEventListener("click", async () => {
        await api("DELETE", "/api/notes/" + note.id);
        state = state.filter((n) => n.id !== note.id);
        render();
      });
      li.append(title, edit, remove);
      return li;
    }

    function render() {
      listEl.replaceChildren(...sorted(state).map(row));
      countEl.textContent = label(state.length);
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      titleEl.disabled = true;
      const created = await api("POST", "/api/notes", { title: titleEl.value });
      titleEl.disabled = false;
      if (!created) return;
      state.push(created);
      form.reset();
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
    if (url.pathname === "/api/notes" && req.method === "POST") {
      const { title = "" } = await readJson(req);
      if (!String(title).trim()) return json(res, 400, { error: "Title is required" });
      const note = { id: nextId++, title: String(title).trim() };
      notes.push(note);
      return json(res, 201, note);
    }
    const match = url.pathname.match(/^\/api\/notes\/(\d+)$/);
    if (match && req.method === "PATCH") {
      const note = notes.find((n) => n.id === Number(match[1]));
      if (!note) return json(res, 404, { error: "Not found" });
      const { title = "" } = await readJson(req);
      if (!String(title).trim()) return json(res, 400, { error: "Title is required" });
      note.title = String(title).trim();
      return json(res, 200, note);
    }
    if (match && req.method === "DELETE") {
      const removedId = Number(match[1]);
      notes = notes.filter((n) => n.id !== removedId);
      return json(res, 200, { ok: true });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      notes = [];
      nextId = 1;
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
