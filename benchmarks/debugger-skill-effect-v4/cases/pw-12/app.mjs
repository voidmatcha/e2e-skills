import { createServer } from "node:http";

const PORT = __PORT__;
const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type });
  res.end(body);
};

const fruit = ["Apple", "Banana", "Cherry"];
const page = `<!doctype html><title>Fruit</title><ol id="list"></ol>
<script>fetch("/api/fruit").then(r=>r.json()).then(rows=>{document.getElementById("list").innerHTML=rows.map(r=>"<li>"+r+"</li>").join("")});</script>`;
function routes(req, res, url) {
  if (url.pathname === "/api/fruit") {
    return send(res, 200, "application/json", JSON.stringify([...fruit].reverse()));
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
