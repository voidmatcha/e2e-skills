import { createServer } from "node:http";

const PORT = __PORT__;
const PAGE_SIZE = 10;
const records = Array.from({ length: 23 }, (_, i) => ({ id: i + 1, name: "Record " + (i + 1) }));

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Records</title></head>
<body>
  <main>
    <h1>Records</h1>
    <ul id="pg-list" aria-label="Records"></ul>
    <nav id="pg-nav" aria-label="Pagination">
      <button type="button" id="pg-prev">Previous</button>
      <span id="pg-status" aria-live="polite"></span>
      <button type="button" id="pg-next">Next</button>
    </nav>
  </main>
  <script>
    const listEl = document.getElementById("pg-list");
    const prevEl = document.getElementById("pg-prev");
    const nextEl = document.getElementById("pg-next");
    const statusEl = document.getElementById("pg-status");
    let state = { page: 1, pages: 1 };

    async function load(pageNumber) {
      const res = await fetch("/api/records?page=" + pageNumber);
      const data = await res.json();
      state = { page: data.page, pages: data.pages };
      listEl.replaceChildren(...data.items.map((r) => {
        const li = document.createElement("li");
        li.className = "record";
        li.textContent = r.name;
        return li;
      }));
      statusEl.textContent = "Page " + data.page + " of " + data.pages;
      prevEl.disabled = data.page <= 1;
      nextEl.disabled = data.page >= data.pages;
    }

    prevEl.addEventListener("click", () => load(state.page - 1));
    nextEl.addEventListener("click", () => load(state.page + 1));
    load(1);
  </script>
</body>
</html>`;

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
  if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
  if (url.pathname === "/api/records" && req.method === "GET") {
    const pages = Math.ceil(records.length / PAGE_SIZE);
    const requested = Number.parseInt(url.searchParams.get("page") || "1", 10);
    const current = Math.min(Math.max(Number.isFinite(requested) ? requested : 1, 1), pages);
    const start = (current - 1) * PAGE_SIZE;
    const items = records.slice(start, start + PAGE_SIZE);
    return json(res, 200, { page: current, pages, total: records.length, items });
  }
  return send(res, 404, "text/plain", "not found");
}).listen(PORT, "127.0.0.1");
