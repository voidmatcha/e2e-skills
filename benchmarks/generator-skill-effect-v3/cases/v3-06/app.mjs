import { createServer } from "node:http";

const PORT = __PORT__;
const seed = () => [
  { id: "groceries", name: "Groceries", limit: 300, spent: 120 },
  { id: "transport", name: "Transport", limit: 150, spent: 150 },
  { id: "fun", name: "Fun", limit: 100, spent: 0 },
];
let envelopes = seed();

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
<head><meta charset="utf-8"><title>Budget envelopes</title></head>
<body>
  <main>
    <h1>Budget envelopes</h1>
    <p id="bg-total" class="total-line">Total $0 of $0</p>
    <div id="bg-envelopes" class="envelopes"></div>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    let state = [];

    async function api(method, path, body) {
      const res = await fetch(path, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      return res.ok ? res.json() : null;
    }

    function card(env) {
      const article = document.createElement("article");
      article.className = env.spent > env.limit ? "envelope over" : "envelope";
      const heading = document.createElement("h2");
      heading.id = "bg-name-" + env.id;
      heading.textContent = env.name;
      const amounts = document.createElement("p");
      amounts.className = "amounts";
      amounts.textContent = "$" + env.spent + " of $" + env.limit;
      const bar = document.createElement("div");
      bar.className = "bar";
      bar.setAttribute("role", "progressbar");
      bar.setAttribute("aria-label", env.name + " spending");
      bar.setAttribute("aria-valuemin", "0");
      bar.setAttribute("aria-valuemax", "100");
      bar.setAttribute("aria-valuenow", String(Math.min(100, Math.round((100 * env.spent) / env.limit))));
      const fill = document.createElement("span");
      fill.className = "bar-fill";
      bar.append(fill);
      const badge = document.createElement("span");
      badge.className = "badge-over";
      badge.textContent = "Over budget";
      badge.hidden = !(env.spent > env.limit);
      const form = document.createElement("div");
      form.className = "spend";
      const labelId = "bg-spend-label-" + env.id;
      const label = document.createElement("span");
      label.id = labelId;
      label.className = "field-label";
      label.textContent = "Add spending";
      const input = document.createElement("input");
      input.inputMode = "numeric";
      input.autocomplete = "off";
      input.setAttribute("aria-labelledby", labelId + " " + heading.id);
      const add = document.createElement("button");
      add.type = "button";
      add.textContent = "Add";
      add.setAttribute("aria-label", "Add spending to " + env.name);
      add.addEventListener("click", async () => {
        const amount = Number(input.value);
        if (!Number.isFinite(amount) || amount <= 0) return;
        const updated = await api("POST", "/api/envelopes/" + env.id + "/spend", { amount });
        if (!updated) return;
        state = state.map((e) => (e.id === updated.id ? updated : e));
        render();
      });
      const reset = document.createElement("button");
      reset.type = "button";
      reset.textContent = "Reset envelope";
      reset.setAttribute("aria-label", "Reset " + env.name);
      reset.addEventListener("click", async () => {
        const updated = await api("POST", "/api/envelopes/" + env.id + "/reset");
        if (!updated) return;
        state = state.map((e) => (e.id === updated.id ? updated : e));
        render();
      });
      form.append(label, input, add, reset);
      article.append(heading, amounts, bar, badge, form);
      return article;
    }

    function render() {
      el("bg-envelopes").replaceChildren(...state.map(card));
      const spent = state.reduce((sum, e) => sum + e.spent, 0);
      const limit = state.reduce((sum, e) => sum + e.limit, 0);
      el("bg-total").textContent = "Total $" + spent + " of $" + limit;
    }

    api("GET", "/api/envelopes").then((list) => { state = list; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/envelopes" && req.method === "GET") return json(res, 200, envelopes);
    const spend = url.pathname.match(/^\/api\/envelopes\/([a-z]+)\/spend$/);
    if (spend && req.method === "POST") {
      const env = envelopes.find((e) => e.id === spend[1]);
      if (!env) return json(res, 404, { error: "Not found" });
      const { amount } = await readJson(req);
      if (!Number.isFinite(Number(amount)) || Number(amount) <= 0) return json(res, 400, { error: "Amount must be positive" });
      env.spent += Math.round(Number(amount));
      return json(res, 200, env);
    }
    const reset = url.pathname.match(/^\/api\/envelopes\/([a-z]+)\/reset$/);
    if (reset && req.method === "POST") {
      const env = envelopes.find((e) => e.id === reset[1]);
      if (!env) return json(res, 404, { error: "Not found" });
      env.spent = 0;
      return json(res, 200, env);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      envelopes = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
