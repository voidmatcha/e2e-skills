import { createServer } from "node:http";

const PORT = __PORT__;
const MAX_TOASTS = 3;
const AUTO_DISMISS_MS = 2000;
let sent = 0;

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Notification settings</title></head>
<body>
  <main>
    <h1>Notification settings</h1>
    <p>Use the button to check that notifications show up on this device.</p>
    <button type="button" id="nt-send">Send test notification</button>
    <p id="nt-count" aria-live="polite">0 sent</p>
  </main>
  <div id="nt-region" role="region" aria-label="Notifications" aria-live="polite"></div>
  <script>
    const MAX_TOASTS = ${MAX_TOASTS};
    const AUTO_DISMISS_MS = ${AUTO_DISMISS_MS};
    const el = (id) => document.getElementById(id);
    let serial = 0;

    function dismiss(toast) {
      if (toast.isConnected) toast.remove();
    }

    function showToast(text) {
      const region = el("nt-region");
      const toast = document.createElement("div");
      toast.className = "toast";
      toast.dataset.serial = String(++serial);
      const message = document.createElement("span");
      message.textContent = text;
      const close = document.createElement("button");
      close.type = "button";
      close.textContent = "×";
      close.setAttribute("aria-label", "Dismiss notification");
      close.addEventListener("click", () => dismiss(toast));
      toast.append(message, close);
      region.append(toast);
      while (region.children.length > MAX_TOASTS) region.firstElementChild.remove();
      setTimeout(() => dismiss(toast), AUTO_DISMISS_MS);
    }

    el("nt-send").addEventListener("click", async () => {
      const res = await fetch("/api/test-notification", { method: "POST" });
      const body = await res.json();
      el("nt-count").textContent = body.sent + " sent";
      showToast("Test notification sent");
    });
  </script>
</body>
</html>`;

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
  if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
  if (url.pathname === "/api/test-notification" && req.method === "POST") {
    sent += 1;
    return json(res, 201, { sent });
  }
  if (url.pathname === "/api/reset" && req.method === "POST") {
    sent = 0;
    return json(res, 200, { ok: true });
  }
  return send(res, 404, "text/plain", "not found");
}).listen(PORT, "127.0.0.1");
