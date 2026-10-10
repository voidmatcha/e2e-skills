import { createServer } from "node:http";

const PORT = __PORT__;
const seed = () => [
  { id: 1, from: "Ada", subject: "Lunch on Friday?", body: "Shall we try the new place by the river?", read: false },
  { id: 2, from: "Grace", subject: "Compiler notes", body: "Attached are the notes from yesterday's session.", read: false },
  { id: 3, from: "Linus", subject: "Patch review", body: "Please look at the second hunk; the first is fine.", read: true },
  { id: 4, from: "Margaret", subject: "Launch checklist", body: "Everything is green except the backup drill.", read: false },
];
let messages = seed();

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Inbox</title></head>
<body>
  <main>
    <h1 id="ib-heading">Inbox (0)</h1>
    <div id="ib-toolbar">
      <input type="checkbox" id="ib-unread-only" name="unreadOnly">
      <label for="ib-unread-only">Unread only</label>
      <button type="button" id="ib-mark-all">Mark all read</button>
    </div>
    <ul id="ib-list" aria-label="Messages"></ul>
    <article id="ib-reader" aria-label="Message" hidden>
      <h2 id="ib-subject"></h2>
      <p id="ib-from"></p>
      <p id="ib-body"></p>
    </article>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    let state = [];
    let openId = null;
    const unreadAtLoad = new Set();

    async function api(method, path) {
      const res = await fetch(path, { method });
      return res.json();
    }

    function render() {
      const unread = state.filter((m) => !m.read).length;
      el("ib-heading").textContent = "Inbox (" + unread + ")";
      const visible = el("ib-unread-only").checked ? state.filter((m) => !m.read) : state;
      el("ib-list").replaceChildren(...visible.map((message) => {
        const li = document.createElement("li");
        li.className = (message.read ? "message read" : "message unread") + (unreadAtLoad.has(message.id) ? " new-since-visit" : "");
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = (message.read ? "" : "● ") + message.subject;
        button.setAttribute("aria-label", (message.read ? "Open " : "Open unread ") + message.subject);
        button.addEventListener("click", () => open(message));
        const from = document.createElement("span");
        from.textContent = " from " + message.from;
        li.append(button, from);
        return li;
      }));
      const current = state.find((m) => m.id === openId);
      el("ib-reader").hidden = !current;
      if (current) {
        el("ib-subject").textContent = current.subject;
        el("ib-from").textContent = "From " + current.from;
        el("ib-body").textContent = current.body;
      }
    }

    async function open(message) {
      openId = message.id;
      const updated = await api("POST", "/api/messages/" + message.id + "/read");
      for (const m of state) if (m.id === updated.id) m.read = true;
      render();
    }

    el("ib-unread-only").addEventListener("change", render);
    el("ib-mark-all").addEventListener("click", async () => {
      await api("POST", "/api/messages/read-all");
      for (const m of state) m.read = true;
      render();
    });

    api("GET", "/api/messages").then((list) => {
      state = list;
      for (const m of state) if (!m.read) unreadAtLoad.add(m.id);
      render();
    });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/messages" && req.method === "GET") return json(res, 200, messages);
    if (url.pathname === "/api/messages/read-all" && req.method === "POST") {
      for (const m of messages) m.read = true;
      return json(res, 200, { ok: true });
    }
    const match = url.pathname.match(/^\/api\/messages\/(\d+)\/read$/);
    if (match && req.method === "POST") {
      const message = messages.find((m) => m.id === Number(match[1]));
      if (!message) return json(res, 404, { error: "Not found" });
      message.read = true;
      return json(res, 200, message);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      messages = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
