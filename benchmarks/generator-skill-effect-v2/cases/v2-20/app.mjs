import { createServer } from "node:http";

const PORT = __PORT__;
const PAGE_SIZE = 10;
const TOTAL = 25;
const seed = () => Array.from({ length: TOTAL }, (_, i) => ({ id: i + 1, title: "Article " + (i + 1), read: false }));
let articles = seed();

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Reading list</title></head>
<body>
  <main>
    <h1>Reading list</h1>
    <div id="rl-toolbar">
      <input type="checkbox" id="rl-hide-read" name="hideRead">
      <label for="rl-hide-read">Hide read</label>
    </div>
    <ul id="rl-list" aria-label="Articles"></ul>
    <p id="rl-count" aria-live="polite"></p>
    <button type="button" id="rl-more">Load more</button>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    let loaded = [];
    let total = 0;

    async function api(method, path) {
      const res = await fetch(path, { method });
      return res.json();
    }

    function render() {
      const hide = el("rl-hide-read").checked;
      const shown = hide ? loaded.filter((a) => !a.read) : loaded;
      el("rl-list").replaceChildren(...shown.map((article) => {
        const li = document.createElement("li");
        li.className = article.read ? "article read" : "article";
        const title = document.createElement("span");
        title.textContent = article.title;
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.textContent = article.read ? "Mark as unread" : "Mark as read";
        toggle.setAttribute("aria-label", (article.read ? "Mark as unread: " : "Mark as read: ") + article.title);
        toggle.addEventListener("click", async () => {
          const updated = await api("POST", "/api/articles/" + article.id + "/" + (article.read ? "unread" : "read"));
          article.read = updated.read;
          render();
        });
        li.append(title, toggle);
        return li;
      }));
      el("rl-count").textContent = "Showing " + shown.length + " of " + total;
      el("rl-more").disabled = loaded.length >= total;
    }

    async function loadMore() {
      const data = await api("GET", "/api/articles?offset=" + loaded.length + "&limit=" + ${PAGE_SIZE});
      loaded = loaded.concat(data.items);
      total = data.total;
      render();
    }

    el("rl-more").addEventListener("click", loadMore);
    el("rl-hide-read").addEventListener("change", render);
    loadMore();
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/articles" && req.method === "GET") {
      const offset = Math.max(0, Number.parseInt(url.searchParams.get("offset") || "0", 10) || 0);
      const limit = Math.min(PAGE_SIZE, Math.max(1, Number.parseInt(url.searchParams.get("limit") || String(PAGE_SIZE), 10) || PAGE_SIZE));
      return json(res, 200, { items: articles.slice(offset, offset + limit), total: articles.length });
    }
    const match = url.pathname.match(/^\/api\/articles\/(\d+)\/(read|unread)$/);
    if (match && req.method === "POST") {
      const article = articles.find((a) => a.id === Number(match[1]));
      if (!article) return json(res, 404, { error: "Not found" });
      article.read = match[2] === "read";
      return json(res, 200, article);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      articles = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
