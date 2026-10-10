import { createServer } from "node:http";
import { randomBytes, randomInt } from "node:crypto";

const PORT = __PORT__;
const MAX_ATTEMPTS = 3;
let codes = new Map();
let sessions = new Map();
let lastCode = null;

const send = (res, status, type, body, headers = {}) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store", ...headers });
  res.end(body);
};
const json = (res, status, body, headers) => send(res, status, "application/json", JSON.stringify(body), headers);
const readJson = async (req) => {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  return raw ? JSON.parse(raw) : {};
};
const sessionOf = (req) => {
  const match = /(?:^|;\s*)sid=([a-f0-9]+)/.exec(req.headers.cookie || "");
  return match ? match[1] : null;
};

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Sign in</title></head>
<body>
  <main>
    <h1 id="pl-title">Sign in</h1>
    <section id="pl-email-step">
      <form id="pl-email-form">
        <label for="pl-email">Email</label>
        <input id="pl-email" name="email" autocomplete="off">
        <button type="submit">Send code</button>
      </form>
    </section>
    <section id="pl-code-step" hidden>
      <p id="pl-sent" role="status"></p>
      <form id="pl-code-form">
        <label for="pl-code">Code</label>
        <input id="pl-code" name="code" autocomplete="off" inputmode="numeric">
        <button type="submit">Sign in</button>
      </form>
      <button type="button" id="pl-new-code">Request a new code</button>
    </section>
    <p id="pl-error" role="alert"></p>
    <section id="pl-account" hidden>
      <p id="pl-whoami"></p>
      <button type="button" id="pl-signout">Sign out</button>
    </section>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    let email = "";

    async function api(method, path, body) {
      const res = await fetch(path, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      return { ok: res.ok, status: res.status, body: await res.json().catch(() => ({})) };
    }

    function show(step) {
      el("pl-email-step").hidden = step !== "email";
      el("pl-code-step").hidden = step !== "code";
      el("pl-account").hidden = step !== "account";
      el("pl-title").textContent = step === "account" ? "Your account" : "Sign in";
    }

    async function requestCode() {
      el("pl-error").textContent = "";
      const result = await api("POST", "/api/codes", { email });
      if (!result.ok) {
        el("pl-error").textContent = result.body.error;
        return;
      }
      el("pl-sent").textContent = "We sent a code to " + email;
      el("pl-code").value = "";
      show("code");
    }

    el("pl-email-form").addEventListener("submit", (event) => {
      event.preventDefault();
      email = el("pl-email").value.trim();
      requestCode();
    });
    el("pl-new-code").addEventListener("click", requestCode);
    el("pl-code-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      el("pl-error").textContent = "";
      const result = await api("POST", "/api/session", { email, code: el("pl-code").value.trim() });
      if (!result.ok) {
        el("pl-error").textContent = result.body.error;
        return;
      }
      el("pl-whoami").textContent = "Signed in as " + result.body.email;
      show("account");
    });
    el("pl-signout").addEventListener("click", async () => {
      await api("DELETE", "/api/session");
      el("pl-email").value = "";
      show("email");
    });

    api("GET", "/api/session").then((result) => {
      if (result.ok) {
        el("pl-whoami").textContent = "Signed in as " + result.body.email;
        show("account");
      }
    });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/codes" && req.method === "POST") {
      const { email = "" } = await readJson(req);
      const normalized = String(email).trim().toLowerCase();
      if (!normalized.includes("@")) return json(res, 400, { error: "Enter your email address" });
      const code = String(randomInt(0, 1000000)).padStart(6, "0");
      codes.set(normalized, { code, used: false, attempts: 0 });
      lastCode = { email: normalized, code };
      return json(res, 201, { sent: true });
    }
    if (url.pathname === "/api/dev/last-code" && req.method === "GET") return json(res, 200, lastCode || {});
    if (url.pathname === "/api/session" && req.method === "GET") {
      const current = sessions.get(sessionOf(req));
      if (!current) return json(res, 401, { error: "Not signed in" });
      return json(res, 200, { email: current });
    }
    if (url.pathname === "/api/session" && req.method === "POST") {
      const { email = "", code = "" } = await readJson(req);
      const normalized = String(email).trim().toLowerCase();
      const issued = codes.get(normalized);
      if (!issued) return json(res, 401, { error: "That code is not right" });
      if (issued.attempts >= MAX_ATTEMPTS) return json(res, 423, { error: "Too many attempts. Request a new code." });
      if (issued.code !== String(code)) {
        issued.attempts += 1;
        if (issued.attempts >= MAX_ATTEMPTS) return json(res, 423, { error: "Too many attempts. Request a new code." });
        return json(res, 401, { error: "That code is not right" });
      }
      if (issued.used) return json(res, 410, { error: "That code was already used" });
      issued.used = true;
      const sid = randomBytes(12).toString("hex");
      sessions.set(sid, normalized);
      return json(res, 201, { email: normalized }, { "set-cookie": "sid=" + sid + "; Path=/; HttpOnly" });
    }
    if (url.pathname === "/api/session" && req.method === "DELETE") {
      sessions.delete(sessionOf(req));
      return json(res, 200, { ok: true }, { "set-cookie": "sid=; Path=/; Max-Age=0" });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      codes = new Map();
      sessions = new Map();
      lastCode = null;
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
