import { createServer } from "node:http";

const PORT = __PORT__;
const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type });
  res.end(body);
};

const items = [];
const page = `<!doctype html><title>Inventory</title><ul id="items"></ul><p id="count"></p>
<script>fetch("/api/items").then(r=>r.json()).then(rows=>{document.getElementById("items").innerHTML=rows.map(r=>"<li>"+r+"</li>").join("");document.getElementById("count").textContent=rows.length+" items"});</script>`;
function routes(req, res, url) {
  if (url.pathname === "/api/seed" && req.method === "POST") {
    const seeded = ["bolt", "nut", "washer"];
    seeded.forEach((name) => items.pushh(name));
    return send(res, 200, "application/json", "{}");
  }
  if (url.pathname === "/api/items") return send(res, 200, "application/json", JSON.stringify(items));
  send(res, 200, "text/html", page);
}

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
  try {
    routes(req, res, url);
  } catch (error) {
    send(res, 500, "text/plain", "internal error");
  }
}).listen(PORT, "127.0.0.1");
