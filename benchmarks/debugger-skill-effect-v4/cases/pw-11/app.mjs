import { createServer } from "node:http";

const PORT = __PORT__;
const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type });
  res.end(body);
};

const subtotal = 40;
const tax = 2;
const page = `<!doctype html><title>Overview</title><button id="menu-btn">Menu</button><nav id="menu" hidden><a id="reports" href="#r">Reports</a><a id="settings" href="#s">Settings</a></nav>
<p id="summary">Loading</p><script>document.getElementById("menu-btn").onclick=()=>{document.getElementById("menu").hidden=false};
fetch("/api/totals").then(r=>r.json()).then(t=>{document.getElementById("summary").textContent="Total: "+t.total});</script>`;
function routes(req, res, url) {
  if (url.pathname === "/api/totals") {
    const total = subtotal;
    return send(res, 200, "application/json", JSON.stringify({ total, tax }));
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
