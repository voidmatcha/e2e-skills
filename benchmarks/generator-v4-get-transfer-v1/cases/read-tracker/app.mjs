// Apache-2.0
import { createServer } from "node:http";

const PORT = __PORT__;
const SEED = [
  { id: "north", title: "North", read: false, opens: 0 },
  { id: "south", title: "South", read: false, opens: 0 },
];
let state = SEED.map((item) => ({ ...item }));

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Reading tracker</title></head>
<body>
  <main>
    <h1>Reading tracker</h1>
    <p id="rt-unread" role="status"></p>
    <ul id="rt-list" aria-label="Titles"></ul>
    <p id="rt-error" role="alert" hidden>Could not open title</p>
  </main>
  <script>
    const unreadEl = document.getElementById("rt-unread");
    const listEl = document.getElementById("rt-list");
    const errorEl = document.getElementById("rt-error");

    function render(items) {
      unreadEl.textContent = "Unread: " + items.filter((item) => !item.read).length;
      listEl.replaceChildren(...items.map((item) => {
        const row = document.createElement("li");
        const label = document.createElement("span");
        label.textContent = item.title + ": " + (item.read ? "Read" : "Unread") + " · " + item.opens + " open" + (item.opens === 1 ? "" : "s");
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Open " + item.title;
        button.addEventListener("click", () => open(item.id));
        row.append(label, " ", button);
        return row;
      }));
    }

    async function open(id) {
      errorEl.hidden = true;
      const response = await fetch("/api/open?id=" + encodeURIComponent(id));
      if (!response.ok) {
        errorEl.hidden = false;
        return;
      }
      render(await response.json());
    }

    fetch("/api/items").then((response) => response.json()).then(render);
  </script>
</body>
</html>`;

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
  if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
  if (url.pathname === "/api/items" && req.method === "GET") return json(res, 200, state);
  if (url.pathname === "/api/open" && req.method === "GET") {
    const id = url.searchParams.get("id");
    const item = state.find((entry) => entry.id === id);
    if (!item) return json(res, 404, { error: "unknown title" });
    item.read = true;
    item.opens += 1;
    return json(res, 200, state);
  }
  if (url.pathname === "/api/reset" && req.method === "POST") {
    state = SEED.map((item) => ({ ...item }));
    return json(res, 200, { ok: true });
  }
  return send(res, 404, "text/plain", "not found");
}).listen(PORT, "127.0.0.1");
