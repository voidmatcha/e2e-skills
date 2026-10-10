// Apache-2.0
import { createServer } from "node:http";

const PORT = __PORT__;
const SEED = { lamp: 3, desk: 3, claimed: 0 };
let stock = { ...SEED };

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Stock claim</title></head>
<body>
  <main>
    <h1>Stock claim</h1>
    <p id="claim-total" role="status"></p>
    <ul id="claim-list" aria-label="Available products"></ul>
    <p id="claim-error" role="alert" hidden>Claim failed</p>
  </main>
  <script>
    const totalEl = document.getElementById("claim-total");
    const listEl = document.getElementById("claim-list");
    const errorEl = document.getElementById("claim-error");
    const names = { lamp: "Lamp", desk: "Desk" };

    function render(next) {
      totalEl.textContent = "Claimed: " + next.claimed;
      listEl.replaceChildren(...Object.keys(names).map((sku) => {
        const row = document.createElement("li");
        const label = document.createElement("span");
        label.textContent = names[sku] + ": " + next[sku] + " left";
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Claim " + names[sku];
        button.addEventListener("click", () => claim(sku));
        row.append(label, " ", button);
        return row;
      }));
    }

    async function claim(sku) {
      errorEl.hidden = true;
      const response = await fetch("/api/claim?sku=" + encodeURIComponent(sku));
      if (!response.ok) {
        errorEl.hidden = false;
        return;
      }
      render(await response.json());
    }

    fetch("/api/stock").then((response) => response.json()).then(render);
  </script>
</body>
</html>`;

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
  if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
  if (url.pathname === "/api/stock" && req.method === "GET") return json(res, 200, stock);
  if (url.pathname === "/api/claim" && req.method === "GET") {
    const sku = url.searchParams.get("sku");
    if (!(sku in stock) || sku === "claimed") return json(res, 404, { error: "unknown product" });
    if (stock[sku] < 1) return json(res, 409, { error: "out of stock" });
    stock[sku] -= 1;
    stock.claimed += 1;
    return json(res, 200, stock);
  }
  if (url.pathname === "/api/reset" && req.method === "POST") {
    stock = { ...SEED };
    return json(res, 200, { ok: true });
  }
  return send(res, 404, "text/plain", "not found");
}).listen(PORT, "127.0.0.1");
