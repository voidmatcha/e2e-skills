import { createServer } from "node:http";

const PORT = __PORT__;
const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type });
  res.end(body);
};

const page = `<!doctype html><title>Counter</title><button id="inc">Increment</button><p>Count: <span id="n">0</span></p>
<script>setTimeout(()=>{let n=0;document.getElementById("inc").addEventListener("click",()=>{n++;document.getElementById("n").textContent=String(n)});document.body.dataset.ready="1";},700);</script>`;
function routes(req, res, url) { send(res, 200, "text/html", page); }

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
  try {
    routes(req, res, url);
  } catch (error) {
    send(res, 500, "text/plain", "internal error");
  }
}).listen(PORT, "127.0.0.1");
