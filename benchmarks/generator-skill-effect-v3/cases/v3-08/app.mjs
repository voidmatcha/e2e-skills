import { createServer } from "node:http";

const PORT = __PORT__;
const ME = "Ada";
const PRIORITIES = ["low", "medium", "high"];
const seed = () => [
  { id: 101, title: "Login page flickers", labels: ["bug"], priority: "medium", assignee: null },
  { id: 102, title: "Add CSV export", labels: ["feature"], priority: "low", assignee: "Grace" },
  { id: 103, title: "Crash on empty cart", labels: ["bug", "urgent"], priority: "high", assignee: null },
  { id: 104, title: "Update onboarding copy", labels: ["docs"], priority: "low", assignee: null },
  { id: 105, title: "Slow search results", labels: ["bug"], priority: "medium", assignee: "Ada" },
];
let issues = seed();

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
<head><meta charset="utf-8"><title>Issues</title></head>
<body>
  <main>
    <h1>Issues</h1>
    <div id="is-filters" class="filters" role="group" aria-label="Filters"></div>
    <div id="is-list" class="issues"></div>
  </main>
  <script>
    const ME = ${JSON.stringify(ME)};
    const PRIORITIES = ${JSON.stringify(PRIORITIES)};
    const RANK = { high: 0, medium: 1, low: 2 };
    const el = (id) => document.getElementById(id);
    let state = [];
    let filter = "all";

    async function api(method, path, body) {
      const res = await fetch(path, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      return res.ok ? res.json() : null;
    }

    function counts() {
      return { all: state.length, mine: state.filter((i) => i.assignee === ME).length, unassigned: state.filter((i) => !i.assignee).length };
    }

    function renderFilters() {
      const c = counts();
      const labels = { all: "All", mine: "Mine", unassigned: "Unassigned" };
      el("is-filters").replaceChildren(...Object.keys(labels).map((key) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = filter === key ? "chip chip-on" : "chip";
        chip.textContent = labels[key] + " (" + c[key] + ")";
        chip.setAttribute("aria-pressed", String(filter === key));
        chip.addEventListener("click", () => { filter = key; render(); });
        return chip;
      }));
    }

    function issueCard(issue) {
      const article = document.createElement("article");
      article.className = "issue priority-" + issue.priority;
      const heading = document.createElement("h2");
      heading.textContent = "#" + issue.id + " " + issue.title;
      const labels = document.createElement("p");
      labels.className = "labels";
      labels.append(...issue.labels.map((l) => { const s = document.createElement("span"); s.className = "label"; s.textContent = l; return s; }));
      const priorityBadge = document.createElement("span");
      priorityBadge.className = "priority";
      priorityBadge.textContent = "Priority: " + issue.priority;
      const select = document.createElement("select");
      select.setAttribute("aria-label", "Priority for " + issue.title);
      for (const p of PRIORITIES) {
        const option = document.createElement("option");
        option.value = p;
        option.textContent = p;
        option.selected = p === issue.priority;
        select.append(option);
      }
      select.addEventListener("change", async () => {
        const updated = await api("PATCH", "/api/issues/" + issue.id, { priority: select.value });
        if (!updated) return;
        state = state.map((i) => (i.id === updated.id ? updated : i));
        render();
      });
      const assignee = document.createElement("span");
      assignee.className = "assignee";
      assignee.textContent = issue.assignee ? "Assigned to " + issue.assignee : "Unassigned";
      const assign = document.createElement("button");
      assign.type = "button";
      const mine = issue.assignee === ME;
      assign.textContent = mine ? "Unassign" : "Assign to me";
      assign.setAttribute("aria-label", (mine ? "Unassign " : "Assign to me: ") + issue.title);
      assign.addEventListener("click", async () => {
        const updated = await api("PATCH", "/api/issues/" + issue.id, { assignee: mine ? null : ME });
        if (!updated) return;
        state = state.map((i) => (i.id === updated.id ? updated : i));
        render();
      });
      article.append(heading, labels, priorityBadge, select, assignee, assign);
      return article;
    }

    function render() {
      renderFilters();
      let visible = state;
      if (filter === "mine") visible = state.filter((i) => i.assignee === ME);
      if (filter === "unassigned") visible = state.filter((i) => !i.assignee);
      const ordered = [...visible].sort((a, b) => RANK[a.priority] - RANK[b.priority] || a.id - b.id);
      el("is-list").replaceChildren(...ordered.map(issueCard));
    }

    api("GET", "/api/issues").then((list) => { state = list; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/issues" && req.method === "GET") return json(res, 200, issues);
    const match = url.pathname.match(/^\/api\/issues\/(\d+)$/);
    if (match && req.method === "PATCH") {
      const issue = issues.find((i) => i.id === Number(match[1]));
      if (!issue) return json(res, 404, { error: "Not found" });
      const body = await readJson(req);
      if ("assignee" in body) issue.assignee = body.assignee ? String(body.assignee) : null;
      if ("priority" in body && PRIORITIES.includes(body.priority)) issue.priority = body.priority;
      return json(res, 200, issue);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      issues = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
