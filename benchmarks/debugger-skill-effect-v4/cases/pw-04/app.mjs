import { createServer } from "node:http";

const PORT = __PORT__;
const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type });
  res.end(body);
};

const page = `<!doctype html><title>Report</title><h1>Quarterly report</h1><p id="total">Loading</p>
<script>fetch("/api/report").then(r=>r.json()).then(d=>{document.getElementById("total").textContent=String(d.total)});</script>`;
function routes(req, res, url) {
  if (url.pathname === "/api/report") {
    return setTimeout(() => send(res, 200, "application/json", JSON.stringify({ total: 42 })), 1500);
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
