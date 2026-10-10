import { createServer } from "node:http";

const PORT = __PORT__;
const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type });
  res.end(body);
};

const cart = [];
const page = `<!doctype html><title>Cart</title><button id="add">Add book</button><p>Items: <span id="count">0</span></p>
<script>const c=document.getElementById("count");const sync=()=>fetch("/api/cart").then(r=>r.json()).then(d=>{c.textContent=String(d.length)});
document.getElementById("add").onclick=()=>fetch("/api/cart",{method:"POST"}).then(sync);sync();</script>`;
function routes(req, res, url) {
  if (url.pathname === "/api/cart") {
    if (req.method === "POST") { cart.push("book"); return send(res, 200, "application/json", "{}"); }
    return send(res, 200, "application/json", JSON.stringify(cart));
  }
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
