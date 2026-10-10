import { createServer } from "node:http";

const PORT = __PORT__;
const COLUMNS = ["Todo", "In progress", "Done"];
const LIMITS = { "In progress": 3 };
const seed = () => [
  { id: 1, title: "Write spec", column: "Todo" },
  { id: 2, title: "Design logo", column: "Todo" },
  { id: 3, title: "Set up CI", column: "Todo" },
  { id: 4, title: "Draft blog post", column: "Todo" },
  { id: 5, title: "Fix login bug", column: "In progress" },
  { id: 6, title: "Review PR 42", column: "In progress" },
  { id: 7, title: "Ship v1.0", column: "Done" },
];
let cards = seed();

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
<head><meta charset="utf-8"><title>Board</title></head>
<body>
  <main>
    <h1>Sprint board</h1>
    <p id="kb-message" role="alert"></p>
    <div id="kb-columns"></div>
  </main>
  <script>
    const COLUMNS = ${JSON.stringify(COLUMNS)};
    const el = (id) => document.getElementById(id);
    let state = [];
    const initialCounts = {};

    async function move(cardId, column) {
      el("kb-message").textContent = "";
      const res = await fetch("/api/cards/" + cardId + "/move", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ column }) });
      const body = await res.json();
      if (!res.ok) {
        el("kb-message").textContent = body.error;
        return;
      }
      const card = state.find((c) => c.id === cardId);
      card.previousColumn = card.column;
      card.column = body.column;
      render();
    }

    function cardNode(card) {
      const li = document.createElement("li");
      li.className = "card";
      li.draggable = true;
      li.dataset.id = card.id;
      li.addEventListener("dragstart", (event) => event.dataTransfer.setData("text/plain", String(card.id)));
      const title = document.createElement("span");
      title.textContent = card.title;
      const select = document.createElement("select");
      select.setAttribute("aria-label", "Move " + card.title);
      for (const column of COLUMNS) {
        const option = document.createElement("option");
        option.value = column;
        option.textContent = column;
        option.selected = column === card.column;
        select.append(option);
      }
      select.addEventListener("change", () => move(card.id, select.value));
      li.append(title, select);
      return li;
    }

    function render() {
      el("kb-columns").replaceChildren(...COLUMNS.map((column) => {
        const section = document.createElement("section");
        section.className = "column";
        section.dataset.column = column;
        const heading = document.createElement("h2");
        const inColumn = state.filter((c) => c.column === column);
        heading.textContent = column + " (" + inColumn.length + ")";
        const list = document.createElement("ul");
        list.setAttribute("aria-label", column);
        list.append(...inColumn.map(cardNode));
        section.append(heading, list);
        section.addEventListener("dragover", (event) => event.preventDefault());
        section.addEventListener("drop", (event) => {
          event.preventDefault();
          const id = Number(event.dataTransfer.getData("text/plain"));
          if (id) move(id, column);
        });
        return section;
      }));
    }

    fetch("/api/cards").then((r) => r.json()).then((list) => {
      state = list;
      for (const column of COLUMNS) initialCounts[column] = state.filter((c) => c.column === column).length;
      document.title = "Board — " + initialCounts["In progress"] + " in progress at open";
      render();
    });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/cards" && req.method === "GET") return json(res, 200, cards);
    const match = url.pathname.match(/^\/api\/cards\/(\d+)\/move$/);
    if (match && req.method === "POST") {
      const card = cards.find((c) => c.id === Number(match[1]));
      if (!card) return json(res, 404, { error: "Not found" });
      const { column } = await readJson(req);
      if (!COLUMNS.includes(column)) return json(res, 400, { error: "Unknown column" });
      const occupancy = cards.filter((c) => c.column === column && c.id !== card.id).length;
      if (LIMITS[column] !== undefined && occupancy >= LIMITS[column]) {
        return json(res, 409, { error: column + " is full (limit " + LIMITS[column] + ")" });
      }
      card.column = column;
      return json(res, 200, card);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      cards = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
