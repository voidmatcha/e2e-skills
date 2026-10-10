import { createServer } from "node:http";

const PORT = __PORT__;
const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type });
  res.end(body);
};

const page = `<!doctype html><title>Shop</title>
<button id="login">Log in</button><div id="panel" hidden>
<p id="who">Signed in as sam</p><a id="orders" href="#orders">Orders</a><button id="logout">Log out</button></div>
<script>document.getElementById("login").onclick=()=>{document.getElementById("panel").hidden=false;document.getElementById("login").hidden=true;};
document.getElementById("logout").onclick=()=>{document.getElementById("panel").hidden=true;document.getElementById("login").hidden=false;};</script>`;
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
