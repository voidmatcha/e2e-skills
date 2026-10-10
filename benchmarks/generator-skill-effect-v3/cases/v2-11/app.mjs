import { createServer } from "node:http";

const PORT = __PORT__;
const seed = () => ["budget.xlsx", "contract.pdf", "draft.docx", "logo.svg", "minutes.txt", "photo.jpg", "roadmap.md"].map((name, i) => ({ id: i + 1, name, deleted: false }));
let files = seed();

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
<head><meta charset="utf-8"><title>Files</title></head>
<body>
  <main>
    <h1>Files</h1>
    <div id="fm-toolbar">
      <span id="fm-selected" aria-live="polite">0 selected</span>
      <button type="button" id="fm-delete" disabled>Delete selected</button>
    </div>
    <table id="fm-table">
      <thead>
        <tr>
          <th scope="col"><input type="checkbox" id="fm-all" aria-label="Select all files"></th>
          <th scope="col">Name</th>
        </tr>
      </thead>
      <tbody id="fm-rows"></tbody>
    </table>
    <div id="fm-toast" role="status" hidden>
      <span id="fm-toast-text"></span>
      <button type="button" id="fm-undo">Undo</button>
    </div>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    let state = [];
    let selected = new Set();
    let lastDeleted = [];

    async function api(method, path, body) {
      const res = await fetch(path, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      return res.json();
    }

    function visible() {
      return state.filter((f) => !f.deleted);
    }

    function render() {
      const rows = visible();
      el("fm-rows").replaceChildren(...rows.map((file) => {
        const tr = document.createElement("tr");
        const cell = document.createElement("td");
        const box = document.createElement("input");
        box.type = "checkbox";
        box.checked = selected.has(file.id);
        box.setAttribute("aria-label", "Select " + file.name);
        box.addEventListener("change", () => {
          if (box.checked) selected.add(file.id); else selected.delete(file.id);
          render();
        });
        cell.append(box);
        const name = document.createElement("td");
        name.textContent = file.name;
        tr.append(cell, name);
        return tr;
      }));
      const count = [...selected].filter((id) => rows.some((f) => f.id === id)).length;
      el("fm-selected").textContent = count + " selected";
      el("fm-delete").disabled = count === 0;
      const all = el("fm-all");
      all.checked = rows.length > 0 && count === rows.length;
      all.indeterminate = count > 0 && count < rows.length;
    }

    el("fm-all").addEventListener("change", () => {
      const rows = visible();
      if (el("fm-all").checked) selected = new Set(rows.map((f) => f.id));
      else selected = new Set();
      render();
    });

    el("fm-delete").addEventListener("click", async () => {
      const ids = [...selected];
      if (!confirm("Delete " + ids.length + " files?")) return;
      await api("POST", "/api/files/delete", { ids });
      for (const f of state) if (ids.includes(f.id)) f.deleted = true;
      lastDeleted = ids;
      selected = new Set();
      el("fm-toast-text").textContent = ids.length + " files deleted";
      el("fm-toast").hidden = false;
      render();
    });

    el("fm-undo").addEventListener("click", async () => {
      const ids = lastDeleted;
      await api("POST", "/api/files/restore", { ids });
      for (const f of state) if (ids.includes(f.id)) f.deleted = false;
      lastDeleted = [];
      el("fm-toast").hidden = true;
      render();
    });

    api("GET", "/api/files").then((list) => { state = list; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/files" && req.method === "GET") return json(res, 200, files);
    if (url.pathname === "/api/files/delete" && req.method === "POST") {
      const { ids = [] } = await readJson(req);
      for (const f of files) if (ids.includes(f.id)) f.deleted = true;
      return json(res, 200, { ok: true });
    }
    if (url.pathname === "/api/files/restore" && req.method === "POST") {
      const { ids = [] } = await readJson(req);
      for (const f of files) if (ids.includes(f.id)) f.deleted = false;
      return json(res, 200, { ok: true });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      files = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
