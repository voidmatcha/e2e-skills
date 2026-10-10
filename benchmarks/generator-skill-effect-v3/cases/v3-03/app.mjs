import { createServer } from "node:http";

const PORT = __PORT__;
const seed = () => [
  { id: 1, name: "Ada Lovelace", role: "Engineer", onLeave: false },
  { id: 2, name: "Grace Hopper", role: "Lead", onLeave: false },
  { id: 3, name: "Linus Torvalds", role: "Engineer", onLeave: true },
  { id: 4, name: "Margaret Hamilton", role: "Manager", onLeave: false },
  { id: 5, name: "Ken Thompson", role: "Engineer", onLeave: false },
];
let members = seed();

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
<head><meta charset="utf-8"><title>Team roster</title></head>
<body>
  <main>
    <h1>Team roster</h1>
    <p id="tr-headcount" class="headcount">0 members · 0 on leave</p>
    <table id="tr-table" class="roster">
      <thead>
        <tr><th scope="col">Name</th><th scope="col">Role</th><th scope="col">Status</th><th scope="col">Actions</th></tr>
      </thead>
      <tbody id="tr-rows"></tbody>
    </table>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    let state = [];
    let confirming = null;

    async function api(method, path, body) {
      const res = await fetch(path, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      return res.ok ? res.json() : null;
    }

    function row(member) {
      const tr = document.createElement("tr");
      tr.className = member.onLeave ? "member away" : "member";
      const name = document.createElement("td");
      name.textContent = member.name;
      const role = document.createElement("td");
      role.textContent = member.role;
      const status = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = member.onLeave ? "badge badge-away" : "badge badge-active";
      badge.textContent = member.onLeave ? "On leave" : "Active";
      status.append(badge);
      const actions = document.createElement("td");
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.textContent = "Toggle leave";
      toggle.setAttribute("aria-label", "Toggle leave for " + member.name);
      toggle.addEventListener("click", async () => {
        const updated = await api("PATCH", "/api/members/" + member.id, { onLeave: !member.onLeave });
        if (!updated) return;
        member.onLeave = updated.onLeave;
        render();
      });
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Remove";
      remove.setAttribute("aria-label", "Remove " + member.name);
      remove.addEventListener("click", () => { confirming = member.id; render(); });
      actions.append(toggle, remove);
      tr.append(name, role, status, actions);
      return tr;
    }

    function confirmRow(member) {
      const tr = document.createElement("tr");
      tr.className = "confirm";
      const td = document.createElement("td");
      td.colSpan = 4;
      const text = document.createElement("span");
      text.className = "confirm-text";
      text.textContent = "Remove " + member.name.split(" ")[0] + "?";
      const yes = document.createElement("button");
      yes.type = "button";
      yes.textContent = "Confirm";
      yes.setAttribute("aria-label", "Confirm removing " + member.name);
      yes.addEventListener("click", async () => {
        await api("DELETE", "/api/members/" + member.id);
        state = state.filter((m) => m.id !== member.id);
        confirming = null;
        render();
      });
      const no = document.createElement("button");
      no.type = "button";
      no.textContent = "Cancel";
      no.setAttribute("aria-label", "Cancel removing " + member.name);
      no.addEventListener("click", () => { confirming = null; render(); });
      td.append(text, yes, no);
      tr.append(td);
      return tr;
    }

    function render() {
      const rows = [];
      for (const member of state) {
        rows.push(row(member));
        if (confirming === member.id) rows.push(confirmRow(member));
      }
      el("tr-rows").replaceChildren(...rows);
      const away = state.filter((m) => m.onLeave).length;
      el("tr-headcount").textContent = state.length + (state.length === 1 ? " member" : " members") + " · " + away + " on leave";
    }

    api("GET", "/api/members").then((list) => { state = list; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/members" && req.method === "GET") return json(res, 200, members);
    const match = url.pathname.match(/^\/api\/members\/(\d+)$/);
    if (match && req.method === "PATCH") {
      const member = members.find((m) => m.id === Number(match[1]));
      if (!member) return json(res, 404, { error: "Not found" });
      const { onLeave } = await readJson(req);
      member.onLeave = Boolean(onLeave);
      return json(res, 200, member);
    }
    if (match && req.method === "DELETE") {
      const removedId = Number(match[1]);
      members = members.filter((m) => m.id !== removedId);
      return json(res, 200, { ok: true });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      members = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
