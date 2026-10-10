import { createServer } from "node:http";

const PORT = __PORT__;
const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type });
  res.end(body);
};

const profiles = { ada: { name: "Ada" } };
const currentUser = "Ada";
const page = `<!doctype html><title>Profile</title><h1 id="hello">Hello</h1><button id="save">Save</button><p id="saved" hidden>Saved</p>
<script>fetch("/api/profile").then(r=>r.json()).then(p=>{document.getElementById("hello").textContent="Hello, "+p.name});
document.getElementById("save").onclick=()=>{document.getElementById("saved").hidden=false};</script>`;
function routes(req, res, url) {
  if (url.pathname === "/api/profile") {
    const profile = profiles[currentUser];
    return send(res, 200, "application/json", JSON.stringify({ name: profile?.name ?? null }));
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
