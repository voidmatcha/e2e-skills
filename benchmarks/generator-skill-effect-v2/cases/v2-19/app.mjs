import { createServer } from "node:http";

const PORT = __PORT__;
const MIN = 2;
const MAX = 30;
let profile = { displayName: "Ada Lovelace" };

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));
const readJson = async (req) => {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  return raw ? JSON.parse(raw) : {};
};

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Profile</title></head>
<body>
  <header id="pf-header">
    <span id="pf-avatar" role="img" aria-label="Avatar"></span>
    <span id="pf-header-name"></span>
  </header>
  <main>
    <h1>Profile</h1>
    <form id="pf-form">
      <label for="pf-name">Display name</label>
      <input id="pf-name" name="displayName" autocomplete="off">
      <button type="submit">Save</button>
    </form>
    <p id="pf-error" role="alert"></p>
    <p id="pf-status" role="status"></p>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    const MIN = ${MIN};
    const MAX = ${MAX};

    function initials(name) {
      const words = name.trim().split(/\\s+/).filter(Boolean);
      if (words.length === 0) return "";
      if (words.length === 1) return words[0][0].toUpperCase();
      return (words[0][0] + words[words.length - 1][0]).toUpperCase();
    }

    function showHeader(name) {
      el("pf-avatar").textContent = initials(name);
      el("pf-header-name").textContent = name;
    }

    el("pf-name").addEventListener("input", () => {
      el("pf-status").textContent = "";
      el("pf-avatar").textContent = initials(el("pf-name").value);
    });

    el("pf-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      el("pf-error").textContent = "";
      const displayName = el("pf-name").value.trim();
      if (displayName.length < MIN || displayName.length > MAX) {
        el("pf-error").textContent = "Name must be " + MIN + "\\u2013" + MAX + " characters";
        return;
      }
      const res = await fetch("/api/profile", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ displayName }) });
      const body = await res.json();
      if (!res.ok) {
        el("pf-error").textContent = body.error;
        return;
      }
      showHeader(body.displayName);
      el("pf-status").textContent = "Profile saved";
    });

    fetch("/api/profile").then((r) => r.json()).then((data) => {
      el("pf-name").value = data.displayName;
      showHeader(data.displayName);
    });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/profile" && req.method === "GET") return json(res, 200, profile);
    if (url.pathname === "/api/profile" && req.method === "PUT") {
      const { displayName = "" } = await readJson(req);
      const name = String(displayName).trim();
      if (name.length < MIN || name.length > MAX) return json(res, 400, { error: "Name must be " + MIN + "–" + MAX + " characters" });
      profile = { displayName: name };
      return json(res, 200, profile);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      profile = { displayName: "Ada Lovelace" };
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
