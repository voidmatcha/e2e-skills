import { createServer } from "node:http";

const PORT = __PORT__;
const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type });
  res.end(body);
};

const page = `<!doctype html><title>Plan</title><p>Current plan: <span id="plan">...</span></p>
<script>fetch("/api/config").then(r=>r.json()).then(c=>{document.getElementById("plan").textContent=c.plan});</script>`;
function routes(req, res, url) {
  if (url.pathname === "/api/config") {
    return setTimeout(() => send(res, 200, "application/json", JSON.stringify({ plan: "free" })), 300);
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
