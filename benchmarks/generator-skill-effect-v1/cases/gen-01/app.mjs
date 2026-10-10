import { createServer } from "node:http";

const PORT = __PORT__;
let entries = [];
let nextId = 1;

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
<head><meta charset="utf-8"><title>Guestbook</title></head>
<body>
  <main>
    <h1>Guestbook</h1>
    <p id="gb-count" aria-live="polite">0 entries</p>
    <form id="gb-form">
      <label for="gb-name">Name</label>
      <input id="gb-name" name="name" autocomplete="off">
      <label for="gb-message">Message</label>
      <input id="gb-message" name="message" autocomplete="off">
      <button type="submit">Sign</button>
    </form>
    <p id="gb-error" role="alert"></p>
    <ul id="gb-list" aria-label="Entries"></ul>
  </main>
  <script>
    const form = document.getElementById("gb-form");
    const nameEl = document.getElementById("gb-name");
    const messageEl = document.getElementById("gb-message");
    const errorEl = document.getElementById("gb-error");
    const listEl = document.getElementById("gb-list");
    const countEl = document.getElementById("gb-count");
    let state = [];

    const label = (n) => (n === 1 ? "1 entry" : n + " entries");

    function render() {
      listEl.innerHTML = "";
      for (const e of state) {
        const li = document.createElement("li");
        li.className = "entry";
        const who = document.createElement("strong");
        who.textContent = e.name;
        const what = document.createElement("span");
        what.textContent = " " + e.message;
        li.append(who, what);
        listEl.append(li);
      }
      countEl.textContent = label(state.length);
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = { name: nameEl.value, message: messageEl.value };
      nameEl.disabled = messageEl.disabled = true;
      const res = await fetch("/api/entries", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await res.json();
      nameEl.disabled = messageEl.disabled = false;
      if (!res.ok) {
        errorEl.textContent = body.error;
        return;
      }
      const created = body;
      state.unshift(created);
      render();
      errorEl.textContent = "";
      form.reset();
    });

    fetch("/api/entries").then((r) => r.json()).then((list) => { state = list; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/entries" && req.method === "GET") return json(res, 200, entries);
    if (url.pathname === "/api/entries" && req.method === "POST") {
      const { name = "", message = "" } = await readJson(req);
      if (!String(name).trim()) return json(res, 400, { error: "Name is required" });
      if (!String(message).trim()) return json(res, 400, { error: "Message is required" });
      const entry = { id: nextId++, name: String(name).trim(), message: String(message).trim() };
      entries.unshift(entry);
      return json(res, 201, entry);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      entries = [];
      nextId = 1;
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
