import { createServer } from "node:http";

const PORT = __PORT__;
const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type });
  res.end(body);
};

const page = `<!doctype html><title>Banner</title><style>#banner{opacity:0;transition:opacity 800ms linear}#banner.on{opacity:1}</style>
<button id="show">Show offer</button><p id="banner">Free shipping today</p>
<script>document.getElementById("show").onclick=()=>document.getElementById("banner").classList.add("on");</script>`;
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
