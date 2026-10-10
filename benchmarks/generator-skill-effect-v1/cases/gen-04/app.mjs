import { createServer } from "node:http";
import { randomBytes } from "node:crypto";

const PORT = __PORT__;

const accounts = [{ email: "ada@example.com", code: "4471", name: "Ada" }];
let sessions = new Map();

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
const cookieId = (req) => {
  const match = /(?:^|;\s*)sid=([a-f0-9]+)/.exec(req.headers.cookie || "");
  return match ? match[1] : null;
};

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Portal</title></head>
<body>
  <main id="si-main">
    <section id="si-form-view">
      <h1>Sign in</h1>
      <form id="si-form">
        <label for="si-email">Email</label>
        <input id="si-email" name="email" autocomplete="off">
        <label for="si-code">Access code</label>
        <input id="si-code" name="code" autocomplete="off">
        <button type="submit">Sign in</button>
      </form>
      <p id="si-error" role="alert"></p>
    </section>
    <section id="si-dashboard" hidden>
      <h1>Dashboard</h1>
      <p id="si-greeting"></p>
      <button type="button" id="si-signout">Sign out</button>
    </section>
  </main>
  <script>
    const formView = document.getElementById("si-form-view");
    const dashboard = document.getElementById("si-dashboard");
    const form = document.getElementById("si-form");
    const emailEl = document.getElementById("si-email");
    const codeEl = document.getElementById("si-code");
    const errorEl = document.getElementById("si-error");
    const greetingEl = document.getElementById("si-greeting");
    const signoutEl = document.getElementById("si-signout");

    function showDashboard(user) {
      greetingEl.textContent = "Welcome, " + user.name;
      formView.hidden = true;
      dashboard.hidden = false;
    }

    function showForm() {
      dashboard.hidden = true;
      formView.hidden = false;
      form.reset();
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      errorEl.textContent = "";
      const res = await fetch("/api/session", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: emailEl.value, code: codeEl.value }),
      });
      const body = await res.json();
      if (!res.ok) {
        errorEl.textContent = body.error;
        return;
      }
      showDashboard(body.user);
    });

    signoutEl.addEventListener("click", async () => {
      await fetch("/api/session", { method: "DELETE" });
      showForm();
    });

    fetch("/api/session").then(async (res) => {
      if (res.ok) showDashboard((await res.json()).user);
    });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/session" && req.method === "GET") {
      const current = sessions.get(cookieId(req));
      if (!current) return json(res, 401, { error: "Not signed in" });
      return json(res, 200, { user: current });
    }
    if (url.pathname === "/api/session" && req.method === "POST") {
      const { email = "", code = "" } = await readJson(req);
      if (!String(email).trim()) return json(res, 400, { error: "Email is required" });
      const account = accounts.find((a) => a.email === String(email).trim().toLowerCase());
      if (!account || account.code !== String(code)) return json(res, 401, { error: "Invalid email or access code" });
      const sid = randomBytes(12).toString("hex");
      sessions.set(sid, { name: account.name, email: account.email });
      return json(res, 201, { user: { name: account.name, email: account.email } }, { "set-cookie": "sid=" + sid + "; Path=/; HttpOnly" });
    }
    if (url.pathname === "/api/session" && req.method === "DELETE") {
      sessions.delete(cookieId(req));
      return json(res, 200, { ok: true }, { "set-cookie": "sid=; Path=/; Max-Age=0" });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      sessions = new Map();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
