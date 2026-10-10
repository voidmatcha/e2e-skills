import { createServer } from "node:http";

const PORT = __PORT__;
const seed = () => [
  { id: 1, title: "Write report", done: false },
  { id: 2, title: "Book flights", done: false },
  { id: 3, title: "Call plumber", done: false },
];
let tasks = seed();

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Task board</title></head>
<body>
  <main>
    <h1>Task board</h1>
    <p id="tb-progress" aria-live="polite"></p>
    <section id="tb-open-section">
      <h2>Open</h2>
      <ul id="tb-open" aria-label="Open tasks"></ul>
    </section>
    <section id="tb-done-section">
      <h2>Done</h2>
      <ul id="tb-done" aria-label="Done tasks"></ul>
    </section>
  </main>
  <script>
    const openEl = document.getElementById("tb-open");
    const doneEl = document.getElementById("tb-done");
    const progressEl = document.getElementById("tb-progress");
    let state = [];

    function replace(updated) {
      state = state.map((t) => (t.id === updated.id ? updated : t));
    }

    function item(task, action) {
      const li = document.createElement("li");
      li.className = "task";
      const title = document.createElement("span");
      title.textContent = task.title;
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = action === "done" ? "Mark done" : "Undo";
      button.setAttribute("aria-label", (action === "done" ? "Mark " : "Undo ") + task.title);
      button.addEventListener("click", async () => {
        const res = await fetch("/api/tasks/" + task.id + "/" + action, { method: "POST" });
        const updated = await res.json();
        replace(updated);
        render();
      });
      li.append(title, button);
      return li;
    }

    function render() {
      openEl.replaceChildren(...state.filter((t) => !t.done).map((t) => item(t, "done")));
      doneEl.replaceChildren(...state.filter((t) => t.done).map((t) => item(t, "undo")));
      const doneCount = state.filter((t) => t.done).length;
      progressEl.textContent = doneCount + " of " + state.length + " done";
    }

    fetch("/api/tasks").then((r) => r.json()).then((list) => { state = list; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/tasks" && req.method === "GET") return json(res, 200, tasks);
    const match = url.pathname.match(/^\/api\/tasks\/(\d+)\/(done|undo)$/);
    if (match && req.method === "POST") {
      const task = tasks.find((t) => t.id === Number(match[1]));
      if (!task) return json(res, 404, { error: "Not found" });
      if (match[2] === "done") {
        const completed = { ...task, done: true };
        Object.assign(task, completed);
        return json(res, 200, completed);
      }
      const reopened = { ...task, done: false };
      Object.assign(task, reopened);
      return json(res, 200, reopened);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      tasks = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
