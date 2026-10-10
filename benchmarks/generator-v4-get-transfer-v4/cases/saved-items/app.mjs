// Apache-2.0
import { createServer } from "node:http";

const PORT = __PORT__;
const SEED = { oak: false, cedar: false };
let saved = { ...SEED };

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Saved items</title></head>
<body>
  <main>
    <h1>Saved items</h1>
    <p id="saved-count" role="status"></p>
    <ul id="saved-list" aria-label="Items"></ul>
    <p id="saved-error" role="alert" hidden>Save failed</p>
  </main>
  <script>
    const countEl = document.getElementById("saved-count");
    const listEl = document.getElementById("saved-list");
    const errorEl = document.getElementById("saved-error");
    const names = { oak: "Oak", cedar: "Cedar" };

    function render(next) {
      countEl.textContent = "Saved: " + Object.values(next).filter(Boolean).length;
      listEl.replaceChildren(...Object.keys(names).map((item) => {
        const row = document.createElement("li");
        const label = document.createElement("span");
        label.textContent = names[item] + ": " + (next[item] ? "Saved" : "Not saved");
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Toggle " + names[item];
        button.addEventListener("click", () => toggle(item));
        row.append(label, " ", button);
        return row;
      }));
    }

    async function toggle(item) {
      errorEl.hidden = true;
      const response = await fetch("/api/toggle?item=" + encodeURIComponent(item));
      if (!response.ok) {
        errorEl.hidden = false;
        return;
      }
      render(await response.json());
    }

    fetch("/api/saved").then((response) => response.json()).then(render);
  </script>
</body>
</html>`;

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
  if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
  if (url.pathname === "/api/saved" && req.method === "GET") return json(res, 200, saved);
  if (url.pathname === "/api/toggle" && req.method === "GET") {
    const item = url.searchParams.get("item");
    if (!(item in saved)) return json(res, 404, { error: "unknown item" });
    saved[item] = !saved[item];
    return json(res, 200, saved);
  }
  if (url.pathname === "/api/reset" && req.method === "POST") {
    saved = { ...SEED };
    return json(res, 200, { ok: true });
  }
  return send(res, 404, "text/plain", "not found");
}).listen(PORT, "127.0.0.1");
