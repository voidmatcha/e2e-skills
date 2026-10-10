import { createServer } from "node:http";

const PORT = __PORT__;
const ME = "Ada";
const seed = () => ({
  messages: [
    { id: 1, author: "Grace", text: "Did the nightly build pass?", quote: null, edited: false },
    { id: 2, author: "Ada", text: "Yes, all green since 02:00.", quote: null, edited: false },
    { id: 3, author: "Linus", text: "Then let's cut the release this afternoon.", quote: null, edited: false },
    { id: 4, author: "Grace", text: "I can prepare the notes.", quote: null, edited: false },
  ],
  lastReadId: 2,
});
let state = seed();
let nextId = 5;

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
<head><meta charset="utf-8"><title>Release thread</title></head>
<body>
  <main>
    <h1 id="th-heading">Release thread</h1>
    <ol id="th-messages" class="messages" aria-label="Messages"></ol>
    <button type="button" id="th-mark-read">Mark as read</button>
    <div id="th-quote" class="quote-box" hidden>
      <span class="quote-label">Replying to</span> <span id="th-quote-text" class="quote-text"></span>
      <button type="button" id="th-cancel-reply">Cancel reply</button>
    </div>
    <div id="th-composer" class="composer">
      <span id="th-composer-label" class="field-label">Your message</span>
      <textarea id="th-input" aria-labelledby="th-composer-label" rows="2"></textarea>
      <button type="button" id="th-send">Send</button>
    </div>
  </main>
  <script>
    const ME = ${JSON.stringify(ME)};
    const el = (id) => document.getElementById(id);
    let data = { messages: [], lastReadId: 0 };
    let replyTo = null;
    let editing = null;

    async function api(method, path, body) {
      const res = await fetch(path, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      return res.ok ? res.json() : null;
    }

    function messageNode(m) {
      const li = document.createElement("li");
      li.className = m.author === ME ? "message mine" : "message";
      if (m.quote) {
        const quote = document.createElement("blockquote");
        quote.className = "quoted";
        quote.textContent = m.quote;
        li.append(quote);
      }
      const author = document.createElement("span");
      author.className = "author";
      author.textContent = m.author + ": ";
      li.append(author);
      if (editing === m.id) {
        const input = document.createElement("input");
        input.value = m.text;
        input.setAttribute("aria-label", "Edit text of message " + m.id);
        const save = document.createElement("button");
        save.type = "button";
        save.textContent = "Save";
        save.setAttribute("aria-label", "Save message " + m.id);
        save.addEventListener("click", async () => {
          const updated = await api("PATCH", "/api/messages/" + m.id, { text: input.value });
          if (!updated) return;
          Object.assign(m, updated);
          editing = null;
          render();
        });
        li.append(input, save);
      } else {
        const text = document.createElement("span");
        text.className = "text";
        text.textContent = m.text + (m.edited ? " (edited)" : "");
        li.append(text);
        const reply = document.createElement("button");
        reply.type = "button";
        reply.textContent = "Reply";
        reply.setAttribute("aria-label", "Reply to message " + m.id);
        reply.addEventListener("click", () => { replyTo = m; render(); el("th-input").focus(); });
        li.append(reply);
        if (m.author === ME) {
          const edit = document.createElement("button");
          edit.type = "button";
          edit.textContent = "Edit";
          edit.setAttribute("aria-label", "Edit message " + m.id);
          edit.addEventListener("click", () => { editing = m.id; render(); });
          li.append(edit);
        }
      }
      return li;
    }

    function render() {
      const nodes = [];
      let dividerPlaced = false;
      const unread = data.messages.filter((m) => m.id > data.lastReadId).length;
      for (const m of data.messages) {
        if (!dividerPlaced && m.id > data.lastReadId && unread > 0) {
          const divider = document.createElement("li");
          divider.className = "divider";
          divider.textContent = unread + (unread === 1 ? " new message" : " new messages");
          nodes.push(divider);
          dividerPlaced = true;
        }
        nodes.push(messageNode(m));
      }
      el("th-messages").replaceChildren(...nodes);
      el("th-heading").textContent = unread ? "Release thread (" + unread + " new)" : "Release thread";
      el("th-mark-read").hidden = unread === 0;
      el("th-quote").hidden = !replyTo;
      el("th-quote-text").textContent = replyTo ? replyTo.author + ": " + replyTo.text : "";
    }

    el("th-cancel-reply").addEventListener("click", () => { replyTo = null; render(); });
    el("th-send").addEventListener("click", async () => {
      const text = el("th-input").value.trim();
      if (!text) return;
      const created = await api("POST", "/api/messages", { text, quote: replyTo ? replyTo.author + ": " + replyTo.text : null });
      if (!created) return;
      data.messages.push(created);
      data.lastReadId = created.id;
      replyTo = null;
      el("th-input").value = "";
      render();
    });
    el("th-mark-read").addEventListener("click", async () => {
      const next = await api("POST", "/api/read");
      if (!next) return;
      data.lastReadId = next.lastReadId;
      render();
    });

    api("GET", "/api/thread").then((d) => { data = d; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/thread" && req.method === "GET") return json(res, 200, state);
    if (url.pathname === "/api/messages" && req.method === "POST") {
      const { text = "", quote = null } = await readJson(req);
      if (!String(text).trim()) return json(res, 400, { error: "Text is required" });
      const message = { id: nextId++, author: ME, text: String(text).trim(), quote: quote ? String(quote) : null, edited: false };
      state.messages.push(message);
      state.lastReadId = message.id;
      return json(res, 201, message);
    }
    const match = url.pathname.match(/^\/api\/messages\/(\d+)$/);
    if (match && req.method === "PATCH") {
      const message = state.messages.find((m) => m.id === Number(match[1]));
      if (!message) return json(res, 404, { error: "Not found" });
      if (message.author !== ME) return json(res, 403, { error: "Not yours" });
      const { text = "" } = await readJson(req);
      if (!String(text).trim()) return json(res, 400, { error: "Text is required" });
      message.text = String(text).trim();
      message.edited = true;
      return json(res, 200, message);
    }
    if (url.pathname === "/api/read" && req.method === "POST") {
      state.lastReadId = state.messages.length ? state.messages[state.messages.length - 1].id : 0;
      return json(res, 200, { lastReadId: state.lastReadId });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      state = seed();
      nextId = 5;
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
