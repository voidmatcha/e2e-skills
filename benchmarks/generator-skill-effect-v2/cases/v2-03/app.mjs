import { createServer } from "node:http";

const PORT = __PORT__;
let comments = [];
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
<head><meta charset="utf-8"><title>Discussion</title></head>
<body>
  <main>
    <h1>Discussion</h1>
    <p id="cm-count" aria-live="polite">0 comments</p>
    <form id="cm-form">
      <label for="cm-text">Your comment</label>
      <input id="cm-text" name="text" autocomplete="off">
      <button type="submit">Post</button>
    </form>
    <ul id="cm-thread" aria-label="Comments"></ul>
  </main>
  <script>
    const form = document.getElementById("cm-form");
    const textEl = document.getElementById("cm-text");
    const threadEl = document.getElementById("cm-thread");
    const countEl = document.getElementById("cm-count");
    let state = [];
    let replyingTo = null;
    let editing = null;

    async function api(method, path, body) {
      const res = await fetch(path, {
        method,
        headers: { "content-type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      return res.ok ? res.json() : null;
    }

    function node(comment) {
      const li = document.createElement("li");
      li.className = "comment";
      li.dataset.id = comment.id;
      if (editing === comment.id) {
        const input = document.createElement("input");
        input.value = comment.text;
        input.setAttribute("aria-label", "New text for comment #" + comment.id);
        const save = document.createElement("button");
        save.type = "button";
        save.textContent = "Save";
        save.setAttribute("aria-label", "Save comment #" + comment.id);
        save.addEventListener("click", async () => {
          const text = input.value;
          await api("PATCH", "/api/comments/" + comment.id, { text });
          comment.text = text;
          editing = null;
          render();
        });
        li.append(input, save);
      } else {
        const text = document.createElement("p");
        text.className = "text";
        text.textContent = "#" + comment.id + " " + comment.text;
        const reply = document.createElement("button");
        reply.type = "button";
        reply.textContent = "Reply";
        reply.setAttribute("aria-label", "Reply to comment #" + comment.id);
        reply.addEventListener("click", () => { replyingTo = comment.id; textEl.focus(); textEl.placeholder = "Replying to #" + comment.id; });
        const edit = document.createElement("button");
        edit.type = "button";
        edit.textContent = "Edit";
        edit.setAttribute("aria-label", "Edit comment #" + comment.id);
        edit.addEventListener("click", () => { editing = comment.id; render(); });
        const del = document.createElement("button");
        del.type = "button";
        del.textContent = "Delete";
        del.setAttribute("aria-label", "Delete comment #" + comment.id);
        del.addEventListener("click", async () => {
          if (!confirm("Delete this comment?")) return;
          await api("DELETE", "/api/comments/" + comment.id);
          state = state.filter((c) => c.id !== comment.id && c.parentId !== comment.id);
          render();
        });
        li.append(text, reply, edit, del);
      }
      const replies = state.filter((c) => c.parentId === comment.id);
      if (replies.length) {
        const ul = document.createElement("ul");
        ul.className = "replies";
        ul.setAttribute("aria-label", "Replies to comment #" + comment.id);
        ul.append(...replies.map(node));
        li.append(ul);
      }
      return li;
    }

    function render() {
      threadEl.replaceChildren(...state.filter((c) => c.parentId === null).map(node));
      const total = state.length;
      countEl.textContent = total === 1 ? "1 comment" : total + " comments";
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const created = await api("POST", "/api/comments", { text: textEl.value, parentId: replyingTo });
      if (!created) return;
      state.push(created);
      replyingTo = null;
      textEl.placeholder = "";
      form.reset();
      render();
    });

    api("GET", "/api/comments").then((list) => { state = list; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/comments" && req.method === "GET") return json(res, 200, comments);
    if (url.pathname === "/api/comments" && req.method === "POST") {
      const { text = "", parentId = null } = await readJson(req);
      if (!String(text).trim()) return json(res, 400, { error: "Text is required" });
      const comment = { id: nextId++, parentId: parentId === null ? null : Number(parentId), text: String(text).trim() };
      comments.push(comment);
      return json(res, 201, comment);
    }
    const match = url.pathname.match(/^\/api\/comments\/(\d+)$/);
    if (match && req.method === "PATCH") {
      const comment = comments.find((c) => c.id === Number(match[1]));
      if (!comment) return json(res, 404, { error: "Not found" });
      const { text = "" } = await readJson(req);
      comment.text = String(text).trim();
      return json(res, 200, comment);
    }
    if (match && req.method === "DELETE") {
      const id = Number(match[1]);
      comments = comments.filter((c) => c.id !== id && c.parentId !== id);
      return json(res, 200, { ok: true });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      comments = [];
      nextId = 1;
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
