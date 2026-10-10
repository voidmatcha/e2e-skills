import { createServer } from "node:http";

const PORT = __PORT__;
const BOOKS = [
  "Algorithms Unlocked", "Alice in Wonderland", "Animal Farm", "Brave New World", "Catch-22", "Dune",
  "Emma", "Fahrenheit 451", "Frankenstein", "Hamlet", "Jane Eyre", "Moby-Dick", "Neuromancer",
  "Odyssey", "Persuasion", "Rebecca", "Sapiens", "The Hobbit", "Ulysses", "Walden",
];
let recent = [];

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Library search</title></head>
<body>
  <main>
    <h1>Library search</h1>
    <label for="ls-query">Search the catalog</label>
    <input id="ls-query" name="q" autocomplete="off">
    <p id="ls-status" role="status"></p>
    <ul id="ls-results" aria-label="Results"></ul>
    <p id="ls-empty" hidden>No titles match</p>
    <section id="ls-recent-section">
      <h2>Recent searches</h2>
      <ul id="ls-recent" aria-label="Recent searches"></ul>
    </section>
  </main>
  <script>
    const queryEl = document.getElementById("ls-query");
    const statusEl = document.getElementById("ls-status");
    const resultsEl = document.getElementById("ls-results");
    const emptyEl = document.getElementById("ls-empty");
    const recentEl = document.getElementById("ls-recent");
    let requestSerial = 0;

    function renderResults(data) {
      resultsEl.replaceChildren(...data.titles.map((title) => {
        const li = document.createElement("li");
        li.textContent = title;
        return li;
      }));
      emptyEl.hidden = data.titles.length > 0 || !data.query;
      statusEl.textContent = data.query ? data.titles.length + " result" + (data.titles.length === 1 ? "" : "s") + " for \\"" + data.query + "\\"" : "";
    }

    function renderRecent(list) {
      recentEl.replaceChildren(...list.map((q) => {
        const li = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = q;
        button.addEventListener("click", () => { queryEl.value = q; search(); });
        li.append(button);
        return li;
      }));
    }

    async function search() {
      const q = queryEl.value.trim();
      if (!q) {
        requestSerial += 1;
        renderResults({ query: "", titles: [] });
        return;
      }
      const serial = ++requestSerial;
      statusEl.textContent = "Searching…";
      const res = await fetch("/api/search?q=" + encodeURIComponent(q));
      const data = await res.json();
      if (serial !== requestSerial) return;
      renderResults(data);
      renderRecent(data.recent);
    }

    queryEl.addEventListener("input", search);
    fetch("/api/recent").then((r) => r.json()).then(renderRecent);
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/recent" && req.method === "GET") return json(res, 200, recent);
    if (url.pathname === "/api/search" && req.method === "GET") {
      const q = (url.searchParams.get("q") || "").trim();
      // short prefixes are slow (large candidate sets); longer queries return quickly
      await sleep(q.length <= 2 ? 700 : 80);
      const titles = BOOKS.filter((title) => title.toLowerCase().includes(q.toLowerCase()));
      if (q.length >= 3) {
        recent = [q, ...recent.filter((item) => item !== q)].slice(0, 5);
      }
      return json(res, 200, { query: q, titles, recent });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      recent = [];
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
