import { createServer } from "node:http";

const PORT = __PORT__;
const seed = () => ({ name: "Ada Lovelace", email: "ada@example.com", deleted: false });
let account = seed();

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Account</title></head>
<body>
  <main>
    <h1>Account</h1>
    <section id="ac-profile">
      <p id="ac-name"></p>
      <p id="ac-email"></p>
      <button type="button" id="ac-open">Delete account</button>
    </section>
    <section id="ac-gone" hidden>
      <p role="status">Your account has been deleted</p>
    </section>
    <div id="ac-dialog" role="dialog" aria-modal="true" aria-labelledby="ac-dialog-title" hidden>
      <h2 id="ac-dialog-title">Delete your account?</h2>
      <p>This cannot be undone. Type <strong>DELETE</strong> to confirm.</p>
      <label for="ac-confirm-text">Type DELETE to confirm</label>
      <input id="ac-confirm-text" autocomplete="off">
      <button type="button" id="ac-cancel">Cancel</button>
      <button type="button" id="ac-confirm" disabled>Delete my account</button>
    </div>
  </main>
  <script>
    const el = (id) => document.getElementById(id);

    function showAccount(data) {
      el("ac-profile").hidden = data.deleted;
      el("ac-gone").hidden = !data.deleted;
      el("ac-name").textContent = data.deleted ? "" : data.name;
      el("ac-email").textContent = data.deleted ? "" : data.email;
    }

    function openDialog() {
      el("ac-confirm-text").value = "";
      el("ac-confirm").disabled = true;
      el("ac-dialog").hidden = false;
      el("ac-confirm-text").focus();
    }

    function closeDialog() {
      el("ac-dialog").hidden = true;
      el("ac-open").focus();
    }

    el("ac-open").addEventListener("click", openDialog);
    el("ac-cancel").addEventListener("click", closeDialog);
    el("ac-confirm-text").addEventListener("input", () => {
      el("ac-confirm").disabled = el("ac-confirm-text").value !== "DELETE";
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !el("ac-dialog").hidden) closeDialog();
    });
    el("ac-confirm").addEventListener("click", async () => {
      const res = await fetch("/api/account", { method: "DELETE" });
      if (!res.ok) return;
      el("ac-dialog").hidden = true;
      showAccount({ deleted: true });
    });

    fetch("/api/account").then((r) => r.json()).then(showAccount);
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/account" && req.method === "GET") return json(res, 200, account);
    if (url.pathname === "/api/account" && req.method === "DELETE") {
      account = { ...account, deleted: true };
      return json(res, 200, { deleted: true });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      account = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
