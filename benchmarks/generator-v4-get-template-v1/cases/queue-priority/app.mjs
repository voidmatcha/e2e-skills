// Apache-2.0
import { createServer } from "node:http";

const PORT = __PORT__;
const SEED = ["raven", "finch"];
let queue = [...SEED];

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Queue priority</title></head>
<body>
  <main>
    <h1>Queue priority</h1>
    <p id="queue-status" role="status"></p>
    <ol id="priority-list" aria-label="Priority order"></ol>
    <button type="button" id="promote-raven">Promote Raven</button>
    <button type="button" id="promote-finch">Promote Finch</button>
    <p id="promotion-error" role="alert" hidden>Promotion failed</p>
  </main>
  <script>
    const statusEl = document.getElementById("queue-status");
    const listEl = document.getElementById("priority-list");
    const errorEl = document.getElementById("promotion-error");
    const names = { raven: "Raven", finch: "Finch" };

    function render(next) {
      statusEl.textContent = "First: " + names[next[0]];
      listEl.replaceChildren(...next.map((item) => {
        const row = document.createElement("li");
        row.textContent = names[item];
        return row;
      }));
    }

    async function promote(item) {
      errorEl.hidden = true;
      const response = await fetch("/api/promote?item=" + encodeURIComponent(item));
      if (!response.ok) {
        errorEl.hidden = false;
        return;
      }
      render(await response.json());
    }

    document.getElementById("promote-raven").addEventListener("click", () => promote("raven"));
    document.getElementById("promote-finch").addEventListener("click", () => promote("finch"));
    fetch("/api/queue").then((response) => response.json()).then(render);
  </script>
</body>
</html>`;

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
  if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
  if (url.pathname === "/api/queue" && req.method === "GET") return json(res, 200, queue);
  if (url.pathname === "/api/promote" && req.method === "GET") {
    const item = url.searchParams.get("item");
    if (!SEED.includes(item)) return json(res, 404, { error: "unknown item" });
    queue = [item, ...queue.filter((entry) => entry !== item)];
    return json(res, 200, queue);
  }
  if (url.pathname === "/api/reset" && req.method === "POST") {
    queue = [...SEED];
    return json(res, 200, { ok: true });
  }
  return send(res, 404, "text/plain", "not found");
}).listen(PORT, "127.0.0.1");
