import { createServer } from "node:http";

const PORT = __PORT__;
const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type });
  res.end(body);
};

const orders = null; // legacy in-memory store, replaced by the new repository in the 5.0 migration
const page = `<!doctype html><title>Orders</title><h1 id="title">Your orders</h1><p id="status">Loading</p><ul id="orders"></ul>
<script>fetch("/api/orders").then(r=>{if(!r.ok)throw new Error(r.status);return r.json()}).then(rows=>{
document.getElementById("status").textContent="";document.getElementById("orders").innerHTML=rows.map(r=>"<li>"+r+"</li>").join("");})
.catch(()=>{document.getElementById("status").textContent="Could not load orders";});</script>`;
function routes(req, res, url) {
  if (url.pathname === "/api/orders") {
    try {
      const rows = orders.list();
      return send(res, 200, "application/json", JSON.stringify(rows));
    } catch (error) {
      return send(res, 500, "application/json", JSON.stringify({ error: "internal" }));
    }
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
