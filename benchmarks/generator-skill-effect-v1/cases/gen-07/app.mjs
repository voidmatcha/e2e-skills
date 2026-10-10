import { createServer } from "node:http";

const PORT = __PORT__;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
let subscribers = new Set();

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
const countLabel = (n) => (n === 1 ? "1 subscriber" : n + " subscribers");

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Newsletter</title></head>
<body>
  <main>
    <h1>Newsletter</h1>
    <p id="nl-count" aria-live="polite"></p>
    <form id="nl-form">
      <label for="nl-email">Email address</label>
      <input id="nl-email" name="email" autocomplete="off">
      <button type="button" id="nl-subscribe">Subscribe</button>
    </form>
    <p id="nl-error" role="alert"></p>
    <p id="nl-success" role="status"></p>
  </main>
  <script>
    const formEl = document.getElementById("nl-form");
    const emailEl = document.getElementById("nl-email");
    const buttonEl = document.getElementById("nl-subscribe");
    const errorEl = document.getElementById("nl-error");
    const successEl = document.getElementById("nl-success");
    const countEl = document.getElementById("nl-count");

    async function submit() {
      const email = emailEl.value;
      const res = await fetch("/api/subscribers", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const body = await res.json();
      if (!res.ok) {
        successEl.textContent = "";
        errorEl.textContent = body.error;
        return;
      }
      errorEl.textContent = "";
      successEl.textContent = "Thanks, you're subscribed";
      countEl.textContent = body.countLabel;
      emailEl.value = "";
    }

    formEl.addEventListener("submit", (event) => event.preventDefault());
    buttonEl.addEventListener("click", submit);
    emailEl.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        submit();
      }
    });

    fetch("/api/subscribers").then((r) => r.json()).then((body) => { countEl.textContent = body.countLabel; });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/subscribers" && req.method === "GET") {
      return json(res, 200, { count: subscribers.size, countLabel: countLabel(subscribers.size) });
    }
    if (url.pathname === "/api/subscribers" && req.method === "POST") {
      const { email = "" } = await readJson(req);
      const normalized = String(email).trim().toLowerCase();
      if (!EMAIL_RE.test(normalized)) return json(res, 400, { error: "Enter a valid email address" });
      if (subscribers.has(normalized)) return json(res, 409, { error: "That email is already subscribed" });
      subscribers.add(normalized);
      return json(res, 201, { email: normalized, count: subscribers.size, countLabel: countLabel(subscribers.size) });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      subscribers = new Set();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
