import { createServer } from "node:http";

const PORT = __PORT__;
const seed = () => [
  { id: 1, name: "Oat milk", bought: false },
  { id: 2, name: "Lemons", bought: false },
  { id: 3, name: "Rye bread", bought: false },
];
let items = seed();
let nextId = 4;

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
<head><meta charset="utf-8"><title>Shopping list</title></head>
<body>
  <main>
    <h1>Shopping list</h1>
    <p id="sl-status" class="status-line">0 items · 0 bought</p>
    <form id="sl-add-form" class="add-row">
      <span id="sl-add-label" class="field-label">New item</span>
      <input id="sl-add-input" aria-labelledby="sl-add-label" autocomplete="off">
      <button type="submit">Add</button>
    </form>
    <ol id="sl-list" class="items" aria-label="Items"></ol>
    <button type="button" id="sl-clear" class="danger" hidden>Clear bought</button>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    let state = [];

    async function api(method, path, body) {
      const res = await fetch(path, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      return res.ok ? res.json() : null;
    }

    function render() {
      const list = el("sl-list");
      list.replaceChildren(...state.map((item, index) => {
        const li = document.createElement("li");
        li.className = item.bought ? "item bought" : "item";
        const pos = document.createElement("span");
        pos.className = "pos";
        pos.textContent = String(index + 1);
        const box = document.createElement("input");
        box.type = "checkbox";
        box.checked = item.bought;
        box.setAttribute("aria-label", "Bought " + item.name);
        box.addEventListener("change", async () => {
          const updated = await api("PATCH", "/api/items/" + item.id, { bought: box.checked });
          item.bought = updated.bought;
          render();
        });
        const name = document.createElement("span");
        name.className = "name";
        name.textContent = item.name;
        const up = document.createElement("button");
        up.type = "button";
        up.textContent = "Move up";
        up.setAttribute("aria-label", "Move " + item.name + " up");
        up.disabled = index === 0;
        up.addEventListener("click", () => move(item.id, -1));
        const down = document.createElement("button");
        down.type = "button";
        down.textContent = "Move down";
        down.setAttribute("aria-label", "Move " + item.name + " down");
        down.disabled = index === state.length - 1;
        down.addEventListener("click", () => move(item.id, 1));
        li.append(pos, box, name, up, down);
        return li;
      }));
      const bought = state.filter((i) => i.bought).length;
      el("sl-status").textContent = state.length + (state.length === 1 ? " item" : " items") + " · " + bought + " bought";
      el("sl-clear").hidden = bought === 0;
    }

    async function move(id, delta) {
      const index = state.findIndex((i) => i.id === id);
      const target = index + delta;
      if (target < 0 || target >= state.length) return;
      const order = state.map((i) => i.id);
      [order[index], order[target]] = [order[target], order[index]];
      const saved = await api("PUT", "/api/order", { order });
      if (!saved) return;
      state = order.map((oid) => state.find((i) => i.id === oid));
      render();
    }

    el("sl-add-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = el("sl-add-input");
      const name = input.value.trim();
      if (!name) return;
      input.disabled = true;
      const created = await api("POST", "/api/items", { name });
      input.disabled = false;
      if (!created) return;
      state.push(created);
      input.value = "";
      render();
    });
    el("sl-clear").addEventListener("click", async () => {
      await api("POST", "/api/items/clear-bought");
      state = state.filter((i) => !i.bought);
      render();
    });

    api("GET", "/api/items").then((list) => { state = list; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/items" && req.method === "GET") return json(res, 200, items);
    if (url.pathname === "/api/items" && req.method === "POST") {
      const { name = "" } = await readJson(req);
      if (!String(name).trim()) return json(res, 400, { error: "Name is required" });
      const item = { id: nextId++, name: String(name).trim(), bought: false };
      items.push(item);
      return json(res, 201, item);
    }
    if (url.pathname === "/api/items/clear-bought" && req.method === "POST") {
      items = items.filter((i) => !i.bought);
      return json(res, 200, { ok: true });
    }
    if (url.pathname === "/api/order" && req.method === "PUT") {
      const { order = [] } = await readJson(req);
      if (order.length !== items.length || order.some((id) => !items.some((i) => i.id === id))) return json(res, 400, { error: "Bad order" });
      items = order.map((id) => items.find((i) => i.id === id));
      return json(res, 200, items);
    }
    const match = url.pathname.match(/^\/api\/items\/(\d+)$/);
    if (match && req.method === "PATCH") {
      const item = items.find((i) => i.id === Number(match[1]));
      if (!item) return json(res, 404, { error: "Not found" });
      const { bought } = await readJson(req);
      item.bought = Boolean(bought);
      return json(res, 200, item);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      items = seed();
      nextId = 4;
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
