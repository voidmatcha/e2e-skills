import { createServer } from "node:http";

const PORT = __PORT__;
const LIMIT = 5;
let tags = [];

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
<head><meta charset="utf-8"><title>Tags</title></head>
<body>
  <main>
    <h1>Article tags</h1>
    <div id="tg-editor">
      <ul id="tg-chips" aria-label="Tags"></ul>
      <label for="tg-input">Add a tag</label>
      <input id="tg-input" name="tag" autocomplete="off">
    </div>
    <p id="tg-message" role="alert"></p>
    <button type="button" id="tg-save">Save</button>
    <p id="tg-status" role="status"></p>
  </main>
  <script>
    const LIMIT = ${LIMIT};
    const el = (id) => document.getElementById(id);
    let state = [];

    function render() {
      el("tg-chips").replaceChildren(...state.map((tag) => {
        const li = document.createElement("li");
        li.className = "chip";
        const text = document.createElement("span");
        text.textContent = tag;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "×";
        remove.setAttribute("aria-label", "Remove " + tag);
        remove.addEventListener("click", () => { state = state.filter((t) => t !== tag); clearMessage(); render(); });
        li.append(text, remove);
        return li;
      }));
      const full = state.length >= LIMIT;
      el("tg-input").disabled = full;
      if (full) el("tg-message").textContent = "Tag limit reached";
    }

    function clearMessage() {
      el("tg-message").textContent = "";
    }

    function add(raw) {
      const tag = raw.trim();
      if (!tag) return;
      if (state.some((t) => t.toLowerCase() === tag.toLowerCase())) {
        el("tg-message").textContent = "Already added";
        return;
      }
      if (state.length >= LIMIT) return;
      state.push(tag);
      el("tg-input").value = "";
      clearMessage();
      el("tg-status").textContent = "";
      render();
    }

    el("tg-input").addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        add(el("tg-input").value);
      } else if (event.key === "Backspace" && el("tg-input").value === "" && state.length) {
        state = state.slice(0, -1);
        clearMessage();
        render();
      }
    });
    el("tg-save").addEventListener("click", async () => {
      const res = await fetch("/api/tags", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ tags: state }) });
      if (res.ok) el("tg-status").textContent = "Tags saved";
    });

    fetch("/api/tags").then((r) => r.json()).then((body) => { state = body.tags; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/tags" && req.method === "GET") return json(res, 200, { tags });
    if (url.pathname === "/api/tags" && req.method === "PUT") {
      const body = await readJson(req);
      const incoming = Array.isArray(body.tags) ? body.tags.map((t) => String(t).trim()).filter(Boolean).slice(0, LIMIT) : [];
      tags = incoming;
      return json(res, 200, { tags });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      tags = [];
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
