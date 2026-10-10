import { createServer } from "node:http";

const PORT = __PORT__;
let draft = { title: "", body: "" };
let posts = [];
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
<head><meta charset="utf-8"><title>Editor</title></head>
<body>
  <main>
    <h1>Editor</h1>
    <form id="ed-form">
      <label for="ed-title">Title</label>
      <input id="ed-title" name="title" autocomplete="off">
      <label for="ed-body">Body</label>
      <textarea id="ed-body" name="body" rows="4"></textarea>
      <p id="ed-status" role="status"></p>
      <button type="submit" id="ed-publish">Publish</button>
      <button type="button" id="ed-discard">Discard draft</button>
    </form>
    <section id="ed-posts-section">
      <h2>Published posts</h2>
      <ul id="ed-posts" aria-label="Published posts"></ul>
    </section>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    const DEBOUNCE_MS = 300;
    let timer = null;

    function snapshot() {
      return { title: el("ed-title").value, body: el("ed-body").value };
    }

    async function saveDraft(payload) {
      const res = await fetch("/api/draft", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) });
      if (res.ok) el("ed-status").textContent = "Draft saved";
    }

    function scheduleSave() {
      el("ed-status").textContent = "Saving…";
      clearTimeout(timer);
      timer = setTimeout(() => saveDraft(snapshot()), DEBOUNCE_MS);
    }

    function renderPosts(list) {
      el("ed-posts").replaceChildren(...list.map((post) => {
        const li = document.createElement("li");
        li.textContent = post.title;
        return li;
      }));
    }

    el("ed-title").addEventListener("input", scheduleSave);
    el("ed-body").addEventListener("input", scheduleSave);
    el("ed-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      clearTimeout(timer);
      const res = await fetch("/api/posts", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(snapshot()) });
      const body = await res.json();
      if (!res.ok) {
        el("ed-status").textContent = body.error;
        return;
      }
      renderPosts(body.posts);
      el("ed-title").value = "";
      el("ed-body").value = "";
      el("ed-status").textContent = "Published";
    });
    el("ed-discard").addEventListener("click", async () => {
      clearTimeout(timer);
      await fetch("/api/draft", { method: "DELETE" });
      el("ed-title").value = "";
      el("ed-body").value = "";
      el("ed-status").textContent = "Draft discarded";
    });

    fetch("/api/state").then((r) => r.json()).then((data) => {
      el("ed-title").value = data.draft.title;
      el("ed-body").value = data.draft.body;
      renderPosts(data.posts);
    });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/state" && req.method === "GET") return json(res, 200, { draft, posts });
    if (url.pathname === "/api/draft" && req.method === "PUT") {
      const body = await readJson(req);
      draft = { title: String(body.title ?? ""), body: String(body.body ?? "") };
      return json(res, 200, draft);
    }
    if (url.pathname === "/api/draft" && req.method === "DELETE") {
      draft = { title: "", body: "" };
      return json(res, 200, draft);
    }
    if (url.pathname === "/api/posts" && req.method === "POST") {
      const body = await readJson(req);
      const title = String(body.title ?? "").trim();
      if (!title) return json(res, 400, { error: "A title is required to publish" });
      posts.push({ id: nextId++, title, body: String(body.body ?? "") });
      draft = { title: "", body: "" };
      return json(res, 201, { posts });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      draft = { title: "", body: "" };
      posts = [];
      nextId = 1;
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
